from __future__ import annotations

import mimetypes
import os
import shlex
from typing import Any

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from astraforge.sandbox.deepagent_backend import SandboxBackend


def _guess_mime_type(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if mime:
        return mime
    # Fallback to a safe default for images when extension is unknown.
    return "image/png"


@tool
def sandbox_view_image(path: str, runtime: ToolRuntime | Any) -> Any:  # pragma: no cover - thin adapter
    """Load an image file from the sandbox and return a LangChain image message.

    The message uses an inline data URL so the vision-enabled model can \"see\" the pixels.
    Use this when you want the model to inspect or describe an image stored under /workspace.
    """
    try:
        backend = SandboxBackend(runtime)
        session = backend._session()
        orchestrator = backend.orchestrator
    except Exception as exc:  # noqa: BLE001
        # Fall back to a plain text message describing the failure.
        return f"Failed to resolve sandbox session for image tool: {exc}"

    # Normalize the path relative to the sandbox workspace.
    root = (
        backend.root_dir.rstrip("/")
        if getattr(backend, "root_dir", None)
        else "/workspace"
    )
    image_path = path
    if not image_path:
        return "No image path provided to sandbox_view_image."
    if not image_path.startswith("/"):
        image_path = f"{root}/{image_path.lstrip('/')}"

    # Read the image bytes from inside the sandbox and base64-encode them.
    cmd = f"base64 < {shlex.quote(image_path)}"
    try:
        result = orchestrator.execute(session, cmd, cwd=None, timeout_sec=30)
    except Exception as exc:  # noqa: BLE001
        return f"Image tool failed to read {image_path!r} inside the sandbox: {exc}"

    if int(result.exit_code) != 0:
        message = (result.stdout or "").strip() or (result.stderr or "").strip()
        if not message:
            message = (
                f"Non-zero exit code {result.exit_code} when reading {image_path!r}"
            )
        return message

    # `base64` may emit newlines; strip surrounding whitespace but preserve the
    # interior so we can safely decode or embed it.
    raw_b64 = (result.stdout or "").strip()
    if not raw_b64:
        return f"Image tool read no data from {image_path!r}."

    # Enforce a maximum payload size so we do not blow up the context window.
    try:
        max_b64_chars = int(os.getenv("IMAGE_TOOL_MAX_BASE64_CHARS", "800000"))
    except (TypeError, ValueError):
        max_b64_chars = 800000
    if len(raw_b64) > max_b64_chars:
        return (
            f"Image at {image_path!r} is too large to inline "
            "safely as base64. Consider resizing or compressing it."
        )

    # Build a data URL that vision models can consume. We rely on the sandbox
    # `base64` utility and do not perform strict validation here, since line
    # breaks in stdout trip Python's `validate=True` flag even when the data
    # itself is correct.
    mime_type = _guess_mime_type(image_path)
    data_url = f"data:{mime_type};base64,{raw_b64}"

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
