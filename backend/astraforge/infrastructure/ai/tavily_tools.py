from __future__ import annotations

import os
from typing import Any, Literal

from langchain.tools import ToolRuntime, tool


@tool
def tavily_web_search(
    query: str,
    topic: Literal["general", "news", "finance"] = "general",
    max_results: int = 5,
    include_raw_content: bool = False,
    runtime: ToolRuntime | Any = None,  # noqa: ARG001 - runtime is injected by DeepAgents
) -> str:  # pragma: no cover - thin wrapper
    """Search the web using Tavily and return concise, source-backed results.

    Use this when you need fresh information from the public internet
    (docs, blogs, API references) that is not available in the local
    workspace or Playwright snapshot.
    """
    # Import inside the function so the module can be imported even if
    # Tavily extras are not installed. This degrades gracefully at runtime.
    try:
        from tavily import TavilyClient
    except Exception as exc:  # noqa: BLE001
        return (
            "Tavily search tool is not available because the Tavily client "
            f"library could not be imported: {exc}"
        )

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return (
            "Tavily search is not configured. "
            "Set the TAVILY_API_KEY environment variable to enable it."
        )

    try:
        client = TavilyClient(api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        return f"Failed to initialize Tavily client: {exc}"

    try:
        results = client.search(
            query,
            max_results=max_results,
            include_raw_content=include_raw_content,
            topic=topic,
        )
    except Exception as exc:  # noqa: BLE001
        return f"Tavily search failed: {exc}"

    # Return the raw Tavily result object (typically a dict with a \"results\" list)
    # so the agent can decide how to post-process or render it.
    return results
