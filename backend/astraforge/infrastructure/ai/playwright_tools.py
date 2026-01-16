from __future__ import annotations

import os
from typing import Any

from langchain.tools import ToolRuntime, tool

from astraforge.sandbox.deepagent_backend import SandboxBackend


@tool
def sandbox_open_url_with_playwright(url: str, **kwargs: Any) -> str:
    """Open a URL in a headless browser **inside the sandbox** and return a brief preview.

    Use this when you need to inspect or summarize a web page.
    """
    runtime = kwargs.get("runtime")
    try:
        backend = SandboxBackend(runtime)
        session = backend._session()
        orchestrator = backend.orchestrator
    except Exception as exc:  # noqa: BLE001
        return f"Playwright sandbox tool could not resolve sandbox session: {exc}"

    # Limit the preview to a safe size to avoid flooding stdout or the LLM context.
    try:
        max_chars = int(os.getenv("PLAYWRIGHT_PREVIEW_MAX_CHARS", "4000"))
    except (TypeError, ValueError):
        max_chars = 4000

    # Python script that runs inside the sandbox container using Playwright.
    script = f"""
python - << 'PY'
from playwright.sync_api import sync_playwright

url = {url!r}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until="networkidle")
    title = page.title()
    try:
        text = page.inner_text("body") or ""
    except Exception:
        # Fallback to text_content or full HTML if inner_text is not available.
        try:
            text = page.text_content("body") or ""
        except Exception:
            text = page.content() or ""
    browser.close()

# Trim on the sandbox side to avoid huge payloads.
max_chars = {max_chars}
if len(text) > max_chars:
    text = text[:max_chars]

print("TITLE:", title)
print("CONTENT_START")
print(text)
PY
"""
    result = orchestrator.execute(
        session,
        script,
        cwd=session.workspace_path,
        timeout_sec=90,
    )
    if result.exit_code != 0:
        message = (result.stdout or "").strip() or (result.stderr or "").strip()
        return f"Playwright sandbox tool failed: {message}"

    stdout = (result.stdout or "").splitlines()
    title = ""
    body_lines: list[str] = []
    reading_body = False
    for line in stdout:
        if line.startswith("TITLE:"):
            title = line[len("TITLE:") :].strip()
            continue
        if line.startswith("CONTENT_START"):
            reading_body = True
            continue
        if reading_body:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()
    if len(body) > max_chars:
        body = body[:max_chars] + "…"

    if not title and not body:
        # Fallback to raw stdout if parsing failed.
        raw = (result.stdout or "").strip()
        return raw or "Playwright sandbox tool completed but produced no output."

    return f"Page title: {title or '(unknown)'}\\n\\nPreview:\\n{body}"
