from __future__ import annotations

import base64
import mimetypes
import os
import shlex
from typing import Any

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from .backend import SandboxBackend


def _guess_mime_type(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if mime:
        return mime
    return "image/png"


def _get_backend(runtime: ToolRuntime | Any) -> SandboxBackend:
    return SandboxBackend(runtime)


@tool
def sandbox_shell(command: str, runtime: ToolRuntime | Any) -> str:
    """Run a shell command inside the sandbox workspace and return its output."""
    try:
        backend = _get_backend(runtime)
    except Exception as exc:  # noqa: BLE001
        return f"Shell sandbox tool could not resolve sandbox session: {exc}"

    command = (command or "").strip()
    if not command:
        return "No shell command provided to sandbox_shell."

    try:
        max_chars = int(os.getenv("SHELL_TOOL_MAX_CHARS", "4000"))
    except (TypeError, ValueError):
        max_chars = 4000

    root = getattr(backend, "root_dir", "/workspace") or "/workspace"
    inner = f"cd {shlex.quote(root)} && {command}"
    script = f"sh -lc {shlex.quote(inner)}"

    try:
        result = backend._shell(script)  # uses remote sandbox API
    except Exception as exc:  # noqa: BLE001
        return f"Shell sandbox tool failed: {exc}"

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    parts: list[str] = []
    parts.append(f"$ cd {root} && {command}")
    if stdout:
        parts.append("[stdout]")
        parts.append(stdout)
    if stderr:
        parts.append("[stderr]")
        parts.append(stderr)
    if not stdout and not stderr:
        parts.append(f"(command exited with code {result.exit_code} and produced no output)")

    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    return text


@tool
def sandbox_python_repl(code: str, runtime: ToolRuntime | Any) -> str:
    """Execute Python code inside the sandbox workspace and return its output."""
    try:
        backend = _get_backend(runtime)
    except Exception as exc:  # noqa: BLE001
        return f"Python REPL sandbox tool could not resolve sandbox session: {exc}"

    try:
        max_chars = int(os.getenv("PYTHON_REPL_MAX_CHARS", "4000"))
    except (TypeError, ValueError):
        max_chars = 4000

    script = f"""
python - << 'PY'
import textwrap

code = textwrap.dedent({code!r})

print(">>> Executing Python in sandbox...")
print(">>> --- code ---")
print(code)
print(">>> --- output ---")

globals_dict = {{}}
locals_dict = globals_dict

try:
    exec(code, globals_dict, locals_dict)
except Exception:
    import traceback
    traceback.print_exc()
PY
"""
    try:
        result = backend._shell(script)
    except Exception as exc:  # noqa: BLE001
        return f"Python REPL sandbox tool failed: {exc}"

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    text = stdout
    if stderr:
        if text:
            text = f"{text}\n\n[stderr]\n{stderr}"
        else:
            text = stderr

    if not text:
        if int(result.exit_code) == 0:
            text = "Python REPL completed successfully with no output."
        else:
            text = f"Python REPL failed with exit code {result.exit_code}."

    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    return text


@tool
def sandbox_open_url_with_playwright(url: str, runtime: ToolRuntime | Any) -> str:
    """Open a URL in a headless browser inside the sandbox and return a brief preview."""
    try:
        backend = _get_backend(runtime)
    except Exception as exc:  # noqa: BLE001
        return f"Playwright sandbox tool could not resolve sandbox session: {exc}"

    try:
        max_chars = int(os.getenv("PLAYWRIGHT_PREVIEW_MAX_CHARS", "4000"))
    except (TypeError, ValueError):
        max_chars = 4000

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
        try:
            text = page.text_content("body") or ""
        except Exception:
            text = page.content() or ""
    browser.close()

max_chars = {max_chars}
if len(text) > max_chars:
    text = text[:max_chars]

print("TITLE:", title)
print("CONTENT_START")
print(text)
PY
"""
    try:
        result = backend._shell(script)
    except Exception as exc:  # noqa: BLE001
        return f"Playwright sandbox tool failed: {exc}"

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
        raw = (result.stdout or "").strip()
        return raw or "Playwright sandbox tool completed but produced no output."

    return f"Page title: {title or '(unknown)'}\n\nPreview:\n{body}"


@tool
def sandbox_view_image(path: str, runtime: ToolRuntime | Any) -> Any:
    """Load an image file from the sandbox and return a LangChain image message."""
    try:
        backend = _get_backend(runtime)
    except Exception as exc:  # noqa: BLE001
        return f"Failed to resolve sandbox session for image tool: {exc}"

    root = backend.root_dir.rstrip("/") if getattr(backend, "root_dir", None) else "/workspace"
    image_path = path
    if not image_path:
        return "No image path provided to sandbox_view_image."
    if not image_path.startswith("/"):
        image_path = f"{root}/{image_path.lstrip('/')}"

    try:
        data = backend.download(image_path)
    except Exception as exc:  # noqa: BLE001
        return f"Image tool failed to read {image_path!r}: {exc}"

    if not data:
        return f"Image tool read no data from {image_path!r}."

    try:
        max_bytes = int(os.getenv("IMAGE_TOOL_MAX_BYTES", "2000000"))
    except (TypeError, ValueError):
        max_bytes = 2000000
    if len(data) > max_bytes:
        return (
            f"Image at {image_path!r} is too large to inline safely. "
            "Consider resizing or compressing it."
        )

    mime_type = _guess_mime_type(image_path)
    b64 = base64.b64encode(data).decode("ascii")
    data_url = f"data:{mime_type};base64,{b64}"

    tool_call_id = getattr(runtime, "tool_call_id", None)
    tool_name = "sandbox_view_image"

    message = ToolMessage(
        content=[
            {
                "type": "text",
                "text": f"Image loaded from sandbox path: {image_path}",
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": data_url,
                },
            },
        ],
        name=tool_name,
        tool_call_id=str(tool_call_id) if tool_call_id is not None else tool_name,
    )

    return Command(update=[message])
