from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, List, Mapping, Optional
from urllib.parse import quote

from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

from astraforge.sandbox.deepagent_backend import SandboxBackend


def _postgres_dsn_from_db_settings(db_settings: Mapping[str, Any]) -> Optional[str]:
    """Build a Postgres DSN from Django database settings."""
    engine = str(db_settings.get("ENGINE") or "").lower()
    if "postgres" not in engine:
        return None
    name = db_settings.get("NAME")
    if not name:
        return None

    user = db_settings.get("USER") or ""
    password = db_settings.get("PASSWORD") or ""
    host = db_settings.get("HOST") or "localhost"
    port = str(db_settings.get("PORT") or "")

    def _quote(value: str) -> str:
        return quote(value, safe="")

    auth = ""
    if user:
        auth = _quote(user)
        if password:
            auth = f"{auth}:{_quote(password)}"
        auth = f"{auth}@"
    elif password:
        auth = f"{_quote(password)}@"

    netloc = host
    if port:
        netloc = f"{netloc}:{port}"

    return f"postgresql://{auth}{netloc}/{_quote(str(name))}"


def _get_database_url_from_django_settings() -> Optional[str]:
    """Return the Postgres DSN configured in Django settings, if available."""
    try:
        from django.conf import settings as django_settings
        from django.core.exceptions import ImproperlyConfigured
    except ImportError:
        return None

    try:
        db_settings = django_settings.DATABASES.get("default")
        print("==> DB SETTINGS:", db_settings)
    except ImproperlyConfigured:
        return None
    if not isinstance(db_settings, Mapping):
        return None
    return _postgres_dsn_from_db_settings(db_settings)


def _get_checkpointer_dsn() -> Optional[str]:
    """Return the DSN for the DeepAgent checkpointer.

    Prefer the explicit override, then the Django database config, then
    fall back to the environment `DATABASE_URL`.
    """
    override = os.getenv("DEEPAGENT_CHECKPOINTER_URL")
    print("==> OVERRIDE:", override)
    if override:
        return override
    return _get_database_url_from_django_settings() or os.getenv("DATABASE_URL")


def _build_checkpointer() -> Optional[Any]:
    """Build an optional Postgres checkpointer for LangGraph.

    When a Postgres connection string is available, this creates a
    `PostgresSaver`, runs its migrations, and returns it.
    If configuration or imports are missing, we silently fall back to
    in-memory execution so DeepAgent still works.
    """
    dsn = _get_checkpointer_dsn()
    if not dsn:
        print("==> CHECKPOINTER: no DSN resolved")
        return None
    try:
        # Local import so missing optional dependencies don't break import-time.
        import psycopg  # type: ignore[import]
        from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore[import]
    except Exception as exc:
        print("==> CHECKPOINTER: missing dependencies", exc)
        return None

    try:
        conn = psycopg.connect(dsn, autocommit=True)
    except Exception as exc:
        print("==> CHECKPOINTER: connection failed", dsn, exc)
        return None

    saver = PostgresSaver(conn)
    try:
        # Idempotent; ensures required tables exist.
        saver.setup()
    except Exception:
        # setup may race across workers; failures should not take down the API.
        return saver
    return saver


def _resolve_deepagent_provider() -> str:
    return (os.getenv("DEEPAGENT_PROVIDER") or os.getenv("LLM_PROVIDER") or "openai").strip().lower()


def _default_deepagent_model(provider: str) -> str:
    configured = os.getenv("DEEPAGENT_MODEL")
    if configured:
        return configured
    if provider == "ollama":
        return os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
    return "gpt-4o"


def _parse_int_env(name: str) -> Optional[int]:
    raw = os.getenv(name)
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logging.getLogger(__name__).warning("Invalid %s value: %s", name, raw)
        return None


def _parse_json_env(name: str) -> dict[str, Any] | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logging.getLogger(__name__).warning("Invalid JSON in %s", name)
        return None
    if not isinstance(data, dict):
        logging.getLogger(__name__).warning("%s must be a JSON object", name)
        return None
    return data


def _build_ollama_model_kwargs() -> dict[str, Any]:
    model_kwargs: dict[str, Any] = {}
    effort = (
        os.getenv("DEEPAGENT_REASONING_EFFORT")
        or os.getenv("OLLAMA_REASONING_EFFORT")
        or ""
    ).strip().lower()
    if effort:
        if effort in {"low", "medium", "high"}:
            model_kwargs["think"] = effort

    num_ctx = _parse_int_env("OLLAMA_NUM_CTX")
    if num_ctx is not None:
        model_kwargs["num_ctx"] = num_ctx
    num_predict = _parse_int_env("OLLAMA_NUM_PREDICT")
    if num_predict is not None:
        model_kwargs["num_predict"] = num_predict

    extra_options = _parse_json_env("OLLAMA_OPTIONS_JSON")
    if extra_options:
        model_kwargs.update(extra_options)

    return model_kwargs


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
        # Single backend class that can operate either in internal mode
        # (local Django sandbox) or HTTP mode (remote AstraForge instance)
        # depending on environment / constructor arguments.
        return SandboxBackend(rt)

    provider = _resolve_deepagent_provider()
    model_name = _default_deepagent_model(provider)
    temperature = float(os.getenv("DEEPAGENT_TEMPERATURE", "0.3"))
    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except Exception as exc:
            raise RuntimeError(
                "langchain-ollama is required for DEEPAGENT_PROVIDER=ollama"
            ) from exc
        base_url = os.getenv("OLLAMA_BASE_URL") or None
        model_kwargs = _build_ollama_model_kwargs()
        ollama_kwargs: dict[str, Any] = {
            "model": model_name,
            "temperature": temperature,
        }
        if base_url:
            ollama_kwargs["base_url"] = base_url
        if model_kwargs:
            ollama_kwargs["model_kwargs"] = model_kwargs
        model = ChatOllama(**ollama_kwargs)
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL") or None
        reasoning_effort = os.getenv("DEEPAGENT_REASONING_EFFORT")
        openai_kwargs: dict[str, Any] = {
            "model": model_name,
            "temperature": temperature,
            "api_key": api_key,
        }
        if base_url:
            openai_kwargs["base_url"] = base_url
        if reasoning_effort:
            openai_kwargs["model_kwargs"] = {"reasoning_effort": reasoning_effort}
        model = ChatOpenAI(**openai_kwargs)
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

    checkpointer = _build_checkpointer()
    print("==> CHECKPOINTER:", checkpointer)
    create_kwargs: dict[str, Any] = {
        "model": model,
        "backend": backend_factory,
        "system_prompt": system_prompt,
        "subagents": subagents,
    }
    if tools:
        create_kwargs["tools"] = tools
    if checkpointer is not None:
        create_kwargs["checkpointer"] = checkpointer

    try:
        return create_deep_agent(**create_kwargs)
    except TypeError as exc:
        # Older DeepAgents versions may not accept a `checkpointer` kwarg.
        if "checkpointer" in str(exc):
            create_kwargs.pop("checkpointer", None)
            return create_deep_agent(**create_kwargs)
        raise
