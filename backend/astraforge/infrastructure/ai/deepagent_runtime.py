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


def _build_python_repl_tools() -> List[Any]:
    """Return Python REPL tools that execute inside the sandbox container."""
    try:
        from astraforge.infrastructure.ai.python_repl_tools import sandbox_python_repl
    except Exception:
        return []
    return [sandbox_python_repl]


def _build_image_tools() -> List[Any]:
    """Return image tools that let the model inspect sandbox images."""
    try:
        from astraforge.infrastructure.ai.image_tools import sandbox_view_image
    except Exception:
        return []
    return [sandbox_view_image]


def _build_shell_tools() -> List[Any]:
    """Return shell tools that run commands inside the sandbox workspace."""
    try:
        from astraforge.infrastructure.ai.shell_tools import sandbox_shell
    except Exception:
        return []
    return [sandbox_shell]


def _build_image_tools() -> List[Any]:
    """Return image tools that let the model inspect sandbox images."""
    try:
        from astraforge.infrastructure.ai.image_tools import sandbox_view_image
    except Exception:
        return []
    return [sandbox_view_image]


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
            "Tavily web search tools to look up external information when necessary, "
            "a Python REPL tool that executes Python code inside the sandbox, "
            "a shell tool that can run short, non-interactive commands inside the sandbox workspace, "
            "and an image tool that can load image files from the sandbox so the vision-enabled model can "
            "inspect them. "
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
    tools.extend(_build_python_repl_tools())
    # tools.extend(_build_image_tools())
    tools.extend(_build_shell_tools())
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
