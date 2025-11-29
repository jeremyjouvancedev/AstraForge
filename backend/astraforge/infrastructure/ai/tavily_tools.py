from __future__ import annotations

import os
from typing import Any

from langchain.tools import ToolRuntime, tool


@tool
def tavily_web_search(query: str, runtime: ToolRuntime | Any) -> str:  # pragma: no cover - thin wrapper
    """Search the web using Tavily and return concise, source-backed results.

    Use this when you need fresh information from the public internet
    (docs, blogs, API references) that is not available in the local
    workspace or Playwright snapshot.
    """
    # Import inside the function so the module can be imported even if
    # Tavily extras are not installed. This degrades gracefully at runtime.
    try:
        from langchain_community.tools.tavily_search import TavilySearchResults
    except Exception as exc:  # noqa: BLE001
        return (
            "Tavily search tool is not available because "
            f"langchain_community Tavily integration could not be imported: {exc}"
        )

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return (
            "Tavily search is not configured. "
            "Set the TAVILY_API_KEY environment variable to enable it."
        )

    try:
        max_results = int(os.getenv("TAVILY_MAX_RESULTS", "5"))
    except (TypeError, ValueError):
        max_results = 5

    try:
        tavily_tool = TavilySearchResults(api_key=api_key, max_results=max_results)
    except Exception as exc:  # noqa: BLE001
        return f"Failed to initialize Tavily search tool: {exc}"

    try:
        # Newer LangChain tools use invoke(); older versions still support run().
        results = tavily_tool.invoke({"query": query})
    except Exception:  # noqa: BLE001
        try:
            results = tavily_tool.run(query)
        except Exception as exc:  # noqa: BLE001
            return f"Tavily search failed: {exc}"

    # TavilySearchResults returns either a string summary or a list of result dicts.
    if isinstance(results, str):
        return results

    try:
        items = list(results)
    except TypeError:
        return str(results)

    if not items:
        return "Tavily search returned no results."

    lines: list[str] = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            lines.append(f"{idx}. {item}")
            continue
        title = item.get("title") or item.get("url") or f"Result {idx}"
        url = item.get("url") or ""
        content = item.get("content") or item.get("snippet") or ""
        block = f"{idx}. {title}"
        if url:
            block += f"\nURL: {url}"
        if content:
            block += f"\nSummary: {content}"
        lines.append(block)

    return "\n\n".join(lines)

