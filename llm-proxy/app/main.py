from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, AsyncIterator, Dict, Iterable

import anyio
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("llm-proxy")

app = FastAPI(title="AstraForge LLM Proxy", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"]
)


class SpecRequest(BaseModel):
    title: str
    description: str
    context: Dict[str, Any] = Field(default_factory=dict)
    repository: str = "unknown"
    branch: str = "main"


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


class MergeRequestResponse(BaseModel):
    title: str
    description: str
    target_branch: str
    source_branch: str


@lru_cache(maxsize=1)
def _create_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured for the LLM proxy")
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def _default_model() -> str:
    return os.getenv("LLM_MODEL", "gpt-4o-mini")


async def _invoke_chat(messages: Iterable[Dict[str, str]], *, response_format: Dict[str, str]) -> str:
    client = _create_client()
    model = _default_model()

    def do_request() -> str:
        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format=response_format,
            messages=list(messages),
        )
        content = response.choices[0].message.content
        if not content:
            raise HTTPException(status_code=502, detail="Empty response from language model")
        return content

    try:
        return await anyio.to_thread.run_sync(do_request)
    except OpenAIError as exc:  # pragma: no cover - upstream failure path
        logger.exception("OpenAI API error: %s", exc)
        raise HTTPException(status_code=502, detail="Upstream model error") from exc


def _openai_responses_url() -> str:
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    return f"{base_url}/responses"


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


async def _proxy_openai_responses(payload: Dict[str, Any]) -> StreamingResponse | Dict[str, Any]:
    url = _openai_responses_url()
    headers = _build_openai_headers()
    timeout = httpx.Timeout(None)
    stream_mode = bool(payload.get("stream"))

    if stream_mode:
        iterator, status_code, response_headers = await _openai_stream_iterator(url, headers, payload, timeout)
        return StreamingResponse(iterator, status_code=status_code, headers=response_headers)

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
        logger.error("OpenAI /responses streaming error %s: %s", upstream.status_code, detail)
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
        raise HTTPException(status_code=502, detail="Invalid response from language model") from exc


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
        raise HTTPException(status_code=502, detail="Invalid response from language model") from exc


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/responses")
async def proxy_responses(request: Request) -> Any:
    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to parse /responses request body")
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    try:
        return await _proxy_openai_responses(payload)
    except RuntimeError as exc:
        logger.exception("/responses configuration error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
