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
        model=model_name,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
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
            "the client can turn them into secure, downloadable links. "
            "For research-backed slide decks or multi-step documentation of a topic, delegate to the "
            "`slide-deck-builder` subagent using the task() tool so it can gather data, create a markdown "
            "plan, and emit one HTML file per slide in the sandbox workspace."
        ),
    )
    tools: list[Any] = []
    tools.extend(_build_playwright_tools())
    tools.extend(_build_tavily_tools())
    tools.extend(_build_python_repl_tools())
    # tools.extend(_build_image_tools())
    tools.extend(_build_shell_tools())
    slide_deck_subagent = {
        "name": "slide-deck-builder",
        "description": (
            "Gathers data for a topic, writes a markdown slide plan, "
            "creates a slide folder, and renders one HTML file per slide "
            "inside the sandbox workspace."
        ),
        "system_prompt": (
            "You are a dedicated slide deck builder operating inside the AstraForge sandbox.\n\n"
            "Your job is to take a user request for a slide deck and execute the following steps:\n"
            "1. Gather data about the topic using available tools such as Tavily web search, "
            "filesystem reads, or short shell commands. Synthesize your research into clear notes "
            "instead of dumping raw data.\n"
            "2. Once you have enough information, create a markdown file under /workspace that contains:\n"
            "   - A 'Plan' section listing each slide title and objective.\n"
            "   - A 'Slides' section where each slide is written as '## Slide N: Title' followed by its content.\n"
            "3. Create a dedicated folder under /workspace (for example `/workspace/slides/<slug>/`) that will "
            "hold the rendered slide files.\n"
            "4. For each slide in the markdown, generate a self-contained HTML file in that folder that "
            "represents that slide. Use simple, responsive HTML with basic CSS so each file can be opened "
            "directly in a browser as an individual slide.\n\n"
            "When interacting with the filesystem, prefer the built-in ls/read_file/write_file/edit_file tools "
            "when available; you can also use the sandbox_shell tool for mkdir and other shell commands if needed. "
            "At the end of the task, return a short summary plus a list of sandbox:workspace/... links to the "
            "markdown plan and all generated HTML files."
        ),
        "tools": tools,
    }
    subagents: list[Any] = [slide_deck_subagent]
    if tools:
        return create_deep_agent(
            model=model,
            backend=backend_factory,
            system_prompt=system_prompt,
            tools=tools,
            subagents=subagents,
        )
    return create_deep_agent(
        model=model,
        backend=backend_factory,
        system_prompt=system_prompt,
        subagents=subagents,
    )
