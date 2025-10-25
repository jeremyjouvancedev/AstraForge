from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Dict, Iterable

import anyio
from fastapi import FastAPI, HTTPException
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
