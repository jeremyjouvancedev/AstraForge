from __future__ import annotations

import os
from typing import Literal

from langchain.tools import tool


@tool
def tavily_web_search(
    query: str,
    topic: Literal["general", "news", "finance"] = "general",
    max_results: int = 5,
    include_raw_content: bool = False,
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

    # Handle custom SSL configuration for corporate environments
    # TavilyClient uses the requests library internally
    import requests
    import requests.api
    import warnings

    # Determine SSL verification setting
    ssl_verify = True

    # Check if SSL verification should be disabled explicitly
    if os.getenv("TAVILY_DISABLE_SSL_VERIFY", "0").lower() in {"1", "true", "yes"}:
        # Disable SSL verification if explicitly requested
        warnings.filterwarnings('ignore', message='Unverified HTTPS request')
        warnings.filterwarnings('ignore', module='urllib3')
        ssl_verify = False
    else:
        # Otherwise, check for custom CA bundle
        ca_bundle = os.getenv("SSL_CERT_FILE") or os.getenv("REQUESTS_CA_BUNDLE")
        if ca_bundle and os.path.exists(ca_bundle):
            # Use custom CA bundle for corporate environments
            ssl_verify = ca_bundle

    # Patch requests.request (the base function that all methods use)
    original_request = requests.api.request

    def patched_request(method, url, **kwargs):
        # Inject our SSL verification setting if not explicitly provided
        if 'verify' not in kwargs:
            kwargs['verify'] = ssl_verify
        return original_request(method, url, **kwargs)

    # Patch at the api module level
    requests.api.request = patched_request
    requests.request = patched_request

    try:
        # Initialize client and perform search
        client = TavilyClient(api_key=api_key)

        results = client.search(
            query,
            max_results=max_results,
            include_raw_content=include_raw_content,
            topic=topic,
        )

        # Return the raw Tavily result object (typically a dict with a "results" list)
        # so the agent can decide how to post-process or render it.
        return results

    except Exception as exc:  # noqa: BLE001
        return f"Tavily search failed: {exc}"

    finally:
        # Always restore original request methods
        requests.api.request = original_request
        requests.request = original_request
