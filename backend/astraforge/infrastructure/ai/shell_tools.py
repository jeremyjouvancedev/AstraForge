from __future__ import annotations

import os
import shlex
from typing import Any

from langchain.tools import ToolRuntime, tool

from astraforge.sandbox.deepagent_backend import SandboxBackend


@tool
def sandbox_shell(command: str, **kwargs: Any) -> str:  # pragma: no cover - thin adapter around sandbox exec
    """Run a shell command inside the sandbox workspace and return its output.

    Use this to run short, self-contained shell commands that operate on files under /workspace.
    Avoid long-running processes and interactive programs.
    """
    runtime = kwargs.get("runtime")
    try:
        backend = SandboxBackend(runtime)
        session = backend._session()
        orchestrator = backend.orchestrator
    except Exception as exc:  # noqa: BLE001
        return f"Shell sandbox tool could not resolve sandbox session: {exc}"

    command = (command or "").strip()
    if not command:
        return "No shell command provided to sandbox_shell."

    try:
        timeout_sec = int(os.getenv("SHELL_TOOL_TIMEOUT_SEC", "60"))
    except (TypeError, ValueError):
        timeout_sec = 60
    try:
        max_chars = int(os.getenv("SHELL_TOOL_MAX_CHARS", "4000"))
    except (TypeError, ValueError):
        max_chars = 4000

    root = getattr(backend, "root_dir", "/workspace") or "/workspace"
    # Use a subshell so we can safely combine cd + command even when the sandbox
    # executor wraps the command with `timeout`. Without the subshell, `timeout`
    # would try to execute `cd` directly and fail.
    inner = f"cd {shlex.quote(root)} && {command}"
    script = f"sh -lc {shlex.quote(inner)}"

    result = orchestrator.execute(
        session,
        script,
        cwd=None,
        timeout_sec=timeout_sec,
    )

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
