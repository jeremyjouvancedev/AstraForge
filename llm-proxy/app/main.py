from __future__ import annotations

import json
import logging
import os
import time
import uuid
from functools import lru_cache
from typing import Any, AsyncIterator, Dict, Iterable, List
from urllib.parse import urlparse, urlunparse

import anyio
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field

logging.basicConfig(level="DEBUG")  # os.getenv("LOG_LEVEL", "DEBUG"))
logger = logging.getLogger("llm-proxy")

app = FastAPI(title="AstraForge LLM Proxy", version="0.2.0", debug=True)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"]
)

_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "host",
}


class SpecRequest(BaseModel):
    title: str
    description: str
    context: Dict[str, Any] = Field(default_factory=dict)
    repository: str = "unknown"
    branch: str = "main"
    reasoning_effort: str | None = None
    reasoning_check: bool | None = None


class SpecResponse(BaseModel):
    title: str
    summary: str
    requirements: list[str]
    implementation_steps: list[str]
    risks: list[str]
    acceptance_criteria: list[str]


class MergeRequestRequest(BaseModel):
    title: str
    repository: str
    target_branch: str
    source_branch: str
    diff: str
    reports: Dict[str, Any] = Field(default_factory=dict)
    reasoning_effort: str | None = None
    reasoning_check: bool | None = None
    reasoning_effort: str | None = None
    reasoning_check: bool | None = None


class MergeRequestResponse(BaseModel):
    title: str
    description: str
    target_branch: str
    source_branch: str


@lru_cache(maxsize=1)
def _llm_provider() -> str:
    return (os.getenv("LLM_PROVIDER") or "ollama").strip().lower()


def _create_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured for the LLM proxy")
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def _default_model() -> str:
    provider = _llm_provider()
    if provider == "ollama":
        return os.getenv("OLLAMA_MODEL") or "devstral-small-2:24b"
    return os.getenv("LLM_MODEL") or "gpt-4o-mini"


def _ollama_base_url() -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    return base_url or "http://localhost:11434"


def _ollama_chat_url() -> str:
    return f"{_ollama_base_url()}/api/chat"


def _is_reasoning_model(model: str) -> bool:
    patterns = ["gpt-oss", "devstral", "deepseek-r1", "o1-", "o3-"]
    return any(model.lower().startswith(p) for p in patterns)


def _should_check_reasoning() -> bool:
    return os.getenv("OLLAMA_REASONING_CHECK", "true").lower() in ("true", "1", "yes")


def _get_reasoning_effort() -> str:
    effort = (
        os.getenv("DEEPAGENT_REASONING_EFFORT")
        or os.getenv("OLLAMA_REASONING_EFFORT")
        or "high"
    ).strip().lower()
    if effort not in {"low", "medium", "high"}:
        return "high"
    return effort


def _openai_base_url() -> str:
    return os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def _anthropic_base_url() -> str:
    return os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")


def _google_base_url() -> str:
    return os.getenv("GOOGLE_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")


def _build_upstream_url(base_url: str, request_path: str, query: str) -> str:
    parsed = urlparse(base_url)
    base_path = parsed.path.rstrip("/")
    if base_path and base_path != "/":
        if request_path == base_path or request_path.startswith(f"{base_path}/"):
            merged_path = request_path
        else:
            merged_path = f"{base_path}{request_path if request_path.startswith('/') else '/' + request_path}"
    else:
        merged_path = request_path
    return urlunparse(parsed._replace(path=merged_path, query=query))


def _filter_headers(headers: Dict[str, str]) -> Dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
    }


async def _proxy_raw_request(
    request: Request, upstream_base_url: str, *, request_path: str | None = None
) -> StreamingResponse:
    body = await request.body()
    path = request_path if request_path is not None else request.url.path
    
    query = request.url.query
    if "generativelanguage.googleapis.com" in upstream_base_url and "key=" not in query:
        google_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if google_api_key:
            query = f"{query}&key={google_api_key}" if query else f"key={google_api_key}"

    upstream_url = _build_upstream_url(
        upstream_base_url, path, query
    )
    headers = _filter_headers(dict(request.headers))

    client = httpx.AsyncClient(timeout=httpx.Timeout(None))
    stream_ctx = client.stream(
        request.method, upstream_url, headers=headers, content=body
    )
    try:
        upstream = await stream_ctx.__aenter__()
    except Exception:
        await client.aclose()
        raise

    response_headers = _filter_headers(dict(upstream.headers))

    async def iterator() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await stream_ctx.__aexit__(None, None, None)
            await client.aclose()

    return StreamingResponse(
        iterator(), status_code=upstream.status_code, headers=response_headers
    )


def _normalize_proxy_path(path: str) -> str:
    if not path:
        return "/"
    if path.startswith("/"):
        return path
    return f"/{path}"


async def _invoke_chat(
    messages: Iterable[Dict[str, str]],
    *,
    response_format: Dict[str, str],
    reasoning_effort: str | None = None,
    reasoning_check: bool | None = None,
) -> str:
    provider = _llm_provider()
    model = _default_model()

    if provider == "ollama":
        payload: Dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "stream": False,
            "options": {"temperature": 0.2},
        }
        effort = reasoning_effort or _get_reasoning_effort()
        check = (
            reasoning_check if reasoning_check is not None else _should_check_reasoning()
        )
        if check or _is_reasoning_model(model):
            payload["options"]["think"] = effort
        if response_format.get("type") == "json_object":
            payload["format"] = "json"
        async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
            response = await client.post(_ollama_chat_url(), json=payload)
        if response.status_code >= 400:
            detail = response.text or "Upstream model error"
            logger.error("Ollama /api/chat error %s: %s", response.status_code, detail)
            raise HTTPException(status_code=response.status_code, detail=detail)
        data = response.json()
        content = data.get("message", {}).get("content")
        if not content:
            raise HTTPException(
                status_code=502, detail="Empty response from language model"
            )
        return str(content)

    if provider != "openai":
        raise HTTPException(
            status_code=400, detail=f"Unsupported LLM provider '{provider}'"
        )

    client = _create_client()

    def do_request() -> str:
        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format=response_format,
            messages=list(messages),
        )
        content = response.choices[0].message.content
        if not content:
            raise HTTPException(
                status_code=502, detail="Empty response from language model"
            )
        return content

    try:
        return await anyio.to_thread.run_sync(do_request)
    except OpenAIError as exc:  # pragma: no cover - upstream failure path
        logger.exception("OpenAI API error: %s", exc)
        raise HTTPException(status_code=502, detail="Upstream model error") from exc


def _openai_responses_url() -> str:
    return f"{_openai_base_url()}/responses"


def _build_openai_headers() -> Dict[str, str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured for the LLM proxy")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    organization = os.getenv("OPENAI_ORG_ID") or os.getenv("OPENAI_ORGANIZATION")
    if organization:
        headers["OpenAI-Organization"] = organization
    project = os.getenv("OPENAI_PROJECT")
    if project:
        headers["OpenAI-Project"] = project
    beta = os.getenv("OPENAI_BETA_HEADERS")
    if beta:
        headers["OpenAI-Beta"] = beta
    return headers


async def _proxy_openai_responses(
    payload: Dict[str, Any],
) -> StreamingResponse | Dict[str, Any]:
    url = _openai_responses_url()
    headers = _build_openai_headers()
    timeout = httpx.Timeout(None)
    stream_mode = bool(payload.get("stream"))

    if stream_mode:
        iterator, status_code, response_headers = await _openai_stream_iterator(
            url, headers, payload, timeout
        )
        return StreamingResponse(
            iterator, status_code=status_code, headers=response_headers
        )

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=headers, json=payload)
    if response.status_code >= 400:
        detail = response.text or "Upstream model error"
        logger.error("OpenAI /responses error %s: %s", response.status_code, detail)
        raise HTTPException(status_code=response.status_code, detail=detail)
    try:
        return response.json()
    except ValueError:  # pragma: no cover - unexpected payload
        logger.warning("OpenAI /responses returned non-JSON payload")
        return {"raw": response.text}


async def _openai_stream_iterator(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    timeout: httpx.Timeout,
) -> tuple[AsyncIterator[bytes], int, Dict[str, str]]:
    client = httpx.AsyncClient(timeout=timeout)
    stream_ctx = client.stream("POST", url, headers=headers, json=payload)
    try:
        upstream = await stream_ctx.__aenter__()
    except Exception:
        await client.aclose()
        raise

    if upstream.status_code >= 400:
        body = await upstream.aread()
        detail = body.decode("utf-8", errors="ignore") or "Upstream model error"
        logger.error(
            "OpenAI /responses streaming error %s: %s", upstream.status_code, detail
        )
        await stream_ctx.__aexit__(None, None, None)
        await client.aclose()
        raise HTTPException(status_code=upstream.status_code, detail=detail)

    response_headers = {
        "Content-Type": upstream.headers.get("content-type", "text/event-stream"),
    }

    async def iterator() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await stream_ctx.__aexit__(None, None, None)
            await client.aclose()

    return iterator(), upstream.status_code, response_headers


def _coerce_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for part in value:
            if isinstance(part, str):
                parts.append(part)
                continue
            if isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    if isinstance(value, dict):
        text = value.get("text") or value.get("content")
        if isinstance(text, str):
            return text
    return ""


def _responses_payload_to_messages(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    messages: list[dict[str, str]] = []
    instructions = payload.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        messages.append({"role": "system", "content": instructions})

    input_payload = payload.get("input")
    if isinstance(input_payload, str):
        messages.append({"role": "user", "content": input_payload})
        return messages

    if isinstance(input_payload, list):
        for item in input_payload:
            if isinstance(item, dict):
                role = item.get("role")
                content = _coerce_content(item.get("content"))
                if isinstance(role, str) and content:
                    messages.append({"role": role, "content": content})
                    continue
            if isinstance(item, str):
                messages.append({"role": "user", "content": item})
        return messages

    if not messages:
        raise HTTPException(
            status_code=400,
            detail="Request body must include input text or message list for Ollama",
        )
    return messages


def _ollama_response_payload(content: str, model: str) -> Dict[str, Any]:
    return {
        "id": f"ollama-{uuid.uuid4()}",
        "object": "response",
        "created": int(time.time()),
        "model": model,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": content}],
            }
        ],
    }


async def _ollama_stream_iterator(
    payload: Dict[str, Any],
) -> tuple[AsyncIterator[bytes], int, Dict[str, str]]:
    model = _default_model()
    messages = _responses_payload_to_messages(payload)
    response_id = f"ollama-{uuid.uuid4()}"
    chat_payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {},
    }
    temperature = payload.get("temperature")
    if isinstance(temperature, (int, float)):
        chat_payload["options"]["temperature"] = temperature
    
    effort = payload.get("reasoning_effort") or _get_reasoning_effort()
    check = payload.get("reasoning_check")
    if check is None:
        check = _should_check_reasoning()

    if check or _is_reasoning_model(model):
        chat_payload["options"]["think"] = effort

    response_format = payload.get("response_format") or {}
    if (
        isinstance(response_format, dict)
        and response_format.get("type") == "json_object"
    ):
        chat_payload["format"] = "json"
    if not chat_payload["options"]:
        chat_payload.pop("options")

    client = httpx.AsyncClient(timeout=httpx.Timeout(None))
    stream_ctx = client.stream("POST", _ollama_chat_url(), json=chat_payload)
    try:
        upstream = await stream_ctx.__aenter__()
    except Exception:
        await client.aclose()
        raise

    if upstream.status_code >= 400:
        body = await upstream.aread()
        detail = body.decode("utf-8", errors="ignore") or "Upstream model error"
        logger.error(
            "Ollama /api/chat streaming error %s: %s", upstream.status_code, detail
        )
        await stream_ctx.__aexit__(None, None, None)
        await client.aclose()
        raise HTTPException(status_code=upstream.status_code, detail=detail)

    response_headers = {"Content-Type": "text/event-stream"}

    async def iterator() -> AsyncIterator[bytes]:
        created_event = {
            "type": "response.created",
            "response": {"id": response_id, "model": model},
        }
        yield f"data: {json.dumps(created_event)}\n\n".encode()
        try:
            async for line in upstream.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("error"):
                    error_event = {"type": "response.error", "error": data["error"]}
                    yield f"data: {json.dumps(error_event)}\n\n".encode()
                    continue
                message = data.get("message") or {}
                delta = message.get("content") or ""
                if delta:
                    delta_event = {
                        "type": "response.output_text.delta",
                        "delta": delta,
                        "response_id": response_id,
                    }
                    yield f"data: {json.dumps(delta_event)}\n\n".encode()
                if data.get("done"):
                    done_event = {
                        "type": "response.output_text.done",
                        "response_id": response_id,
                    }
                    complete_event = {
                        "type": "response.completed",
                        "response": {"id": response_id, "status": "completed"},
                    }
                    yield f"data: {json.dumps(done_event)}\n\n".encode()
                    yield f"data: {json.dumps(complete_event)}\n\n".encode()
                    break
        finally:
            await stream_ctx.__aexit__(None, None, None)
            await client.aclose()

    return iterator(), upstream.status_code, response_headers


async def _proxy_ollama_responses(
    payload: Dict[str, Any],
) -> StreamingResponse | Dict[str, Any]:
    stream_mode = bool(payload.get("stream"))
    if stream_mode:
        iterator, status_code, response_headers = await _ollama_stream_iterator(payload)
        return StreamingResponse(
            iterator, status_code=status_code, headers=response_headers
        )

    model = _default_model()
    messages = _responses_payload_to_messages(payload)
    chat_payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {},
    }
    temperature = payload.get("temperature")
    if isinstance(temperature, (int, float)):
        chat_payload["options"]["temperature"] = temperature
    
    effort = payload.get("reasoning_effort") or _get_reasoning_effort()
    check = payload.get("reasoning_check")
    if check is None:
        check = _should_check_reasoning()

    if check or _is_reasoning_model(model):
        chat_payload["options"]["think"] = effort

    response_format = payload.get("response_format") or {}
    if (
        isinstance(response_format, dict)
        and response_format.get("type") == "json_object"
    ):
        chat_payload["format"] = "json"
    if not chat_payload["options"]:
        chat_payload.pop("options")

    async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
        response = await client.post(_ollama_chat_url(), json=chat_payload)
    if response.status_code >= 400:
        detail = response.text or "Upstream model error"
        logger.error("Ollama /api/chat error %s: %s", response.status_code, detail)
        raise HTTPException(status_code=response.status_code, detail=detail)
    data = response.json()
    content = data.get("message", {}).get("content")
    if not content:
        raise HTTPException(
            status_code=502, detail="Empty response from language model"
        )
    return _ollama_response_payload(str(content), model)


@app.post("/spec", response_model=SpecResponse)
async def generate_spec(request: SpecRequest) -> SpecResponse:
    system_prompt = (
        "You are a senior staff engineer. Expand the user's request into a complete development "
        "specification for the implementation team. Respond strictly with JSON containing the keys: "
        "title, summary, requirements (array), implementation_steps (array), risks (array), acceptance_criteria (array)."
    )
    user_prompt = (
        f"User request title: {request.title}\n\n"
        f"User request description: {request.description}\n\n"
        f"Context (JSON): {request.context}\n\n"
        f"Repository: {request.repository}\nBranch: {request.branch}\n"
        "Clarify ambiguous goals, surface follow-up risks, and ensure acceptance criteria are testable."
    )

    content = await _invoke_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    try:
        return SpecResponse.model_validate_json(content)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to parse spec response: %s", content)
        raise HTTPException(
            status_code=502, detail="Invalid response from language model"
        ) from exc


@app.post("/merge-request", response_model=MergeRequestResponse)
async def compose_merge_request(request: MergeRequestRequest) -> MergeRequestResponse:
    system_prompt = (
        "You are a release engineer preparing a merge request summary. Respond strictly with JSON "
        "containing title, description, target_branch, source_branch. The description must highlight key changes, "
        "testing performed, and known risks."
    )
    user_prompt = (
        f"Original request title: {request.title}\n"
        f"Repository: {request.repository}\n"
        f"Target branch: {request.target_branch}\n"
        f"Workspace branch: {request.source_branch}\n"
        f"Diff summary: {request.diff[:4000]}\n"
        f"Reports: {request.reports}\n"
        "Craft a concise merge request body with sections for Summary, Testing, and Risks."
    )

    content = await _invoke_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    try:
        return MergeRequestResponse.model_validate_json(content)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to parse merge request response: %s", content)
        raise HTTPException(
            status_code=502, detail="Invalid response from language model"
        ) from exc


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route(
    "/providers/{provider}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_provider_request(
    provider: str, path: str, request: Request
) -> StreamingResponse:
    provider_key = provider.strip().lower()
    if provider_key == "openai":
        upstream_base_url = _openai_base_url()
    elif provider_key == "ollama":
        upstream_base_url = _ollama_base_url()
    elif provider_key == "anthropic":
        upstream_base_url = _anthropic_base_url()
    elif provider_key == "google":
        upstream_base_url = _google_base_url()
    else:
        raise HTTPException(
            status_code=404, detail=f"Unsupported LLM provider '{provider}'"
        )
    if not path:
        raise HTTPException(status_code=400, detail="Provider subpath is required")
    trimmed_path = path.strip("/")
    if provider_key == "ollama" and trimmed_path in {"responses", "v1/responses"}:
        try:
            payload = await request.json()
        except Exception as exc:  # noqa: BLE001 - invalid payload
            raise HTTPException(
                status_code=400, detail="Invalid JSON payload for responses request"
            ) from exc
        return await _proxy_ollama_responses(payload)
    request_path = _normalize_proxy_path(path)
    return await _proxy_raw_request(
        request, upstream_base_url, request_path=request_path
    )


@app.api_route("/responses", methods=["POST"])
async def proxy_openai_responses(request: Request) -> StreamingResponse:
    return await _proxy_raw_request(request, _openai_base_url())


@app.api_route("/v1/responses", methods=["POST"])
async def proxy_openai_responses_v1(request: Request) -> StreamingResponse:
    return await _proxy_raw_request(request, _openai_base_url())


@app.api_route("/chat/completions", methods=["POST"])
async def proxy_ollama_chat_completions(request: Request) -> StreamingResponse:
    return await _proxy_raw_request(request, _ollama_base_url())


@app.api_route("/v1/chat/completions", methods=["POST"])
async def proxy_ollama_chat_completions_v1(request: Request) -> StreamingResponse:
    return await _proxy_raw_request(request, _ollama_base_url())
