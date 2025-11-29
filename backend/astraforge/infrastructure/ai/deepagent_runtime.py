from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, List

from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

from astraforge.sandbox.deepagent_backend import SandboxBackend


def _build_playwright_tools() -> List[Any]:
    """Return Playwright tools that execute inside the sandbox container."""
    try:
        from astraforge.infrastructure.ai.playwright_tools import (
            sandbox_open_url_with_playwright,
        )
    except Exception:
        return []
    return [sandbox_open_url_with_playwright]


def _build_tavily_tools() -> List[Any]:
    """Return Tavily web search tools if available."""
    try:
        from astraforge.infrastructure.ai.tavily_tools import tavily_web_search
    except Exception:
        return []
    return [tavily_web_search]


@lru_cache(maxsize=1)
def get_deep_agent():
    """Instantiate a singleton deep agent bound to the sandbox backend."""

    def backend_factory(rt):
        return SandboxBackend(rt)

    model_name = os.getenv("DEEPAGENT_MODEL", "gpt-4o")
    temperature = float(os.getenv("DEEPAGENT_TEMPERATURE", "0.3"))
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL") or None
    model = ChatOpenAI(
        model=model_name, temperature=temperature, api_key=api_key, base_url=base_url
    )
    system_prompt = os.getenv(
        "DEEPAGENT_SYSTEM_PROMPT",
        (
            "You are a deep coding agent operating inside an isolated sandbox. "
            "Use filesystem tools (ls, read_file, write_file, edit_file, glob, grep) "
            "to explore and modify files in /workspace as needed. "
            "You also have access to Playwright browser tools to visit and inspect web pages, "
            "and Tavily web search tools to look up external information when necessary. "
            "Respond using GitHub-flavored Markdown so the UI can render headings, lists, and code blocks. "
            "When you want the user to download a file from the sandbox, emit a Markdown link using the "
            "sandbox: scheme, where the path is relative to /workspace. For example: "
            "[summary.md](sandbox:workspace/summary.md) for /workspace/summary.md, or "
            "[report.txt](sandbox:workspace/reports/report.txt) for /workspace/reports/report.txt. "
            "Do not emit direct HTTP URLs for sandbox files; always use sandbox:workspace/... links so "
            "the client can turn them into secure, downloadable links."
        ),
    )
    tools: list[Any] = []
    tools.extend(_build_playwright_tools())
    tools.extend(_build_tavily_tools())
    if tools:
        return create_deep_agent(
            model=model,
            backend=backend_factory,
            system_prompt=system_prompt,
            tools=tools,
        )
    return create_deep_agent(
        model=model, backend=backend_factory, system_prompt=system_prompt
    )
