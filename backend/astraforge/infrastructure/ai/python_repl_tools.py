from __future__ import annotations

import os
from typing import Any

from langchain.tools import tool

from astraforge.sandbox.deepagent_backend import SandboxBackend


@tool
def sandbox_python_repl(code: str, **kwargs: Any) -> str:  # pragma: no cover - thin adapter around sandbox exec
    """Execute Python code inside the sandbox workspace and return its output.

    Use this to run short Python snippets that work with files under /workspace.
    The environment is isolated per sandbox session; use the filesystem if you
    need to persist state between calls.
    """
    runtime = kwargs.get("runtime")
    try:
        backend = SandboxBackend(runtime)
        session = backend._session()
        orchestrator = backend.orchestrator
    except Exception as exc:  # noqa: BLE001
        return f"Python REPL sandbox tool could not resolve sandbox session: {exc}"

    try:
        max_chars = int(os.getenv("PYTHON_REPL_MAX_CHARS", "4000"))
    except (TypeError, ValueError):
        max_chars = 4000

    # Execute the user code inside the sandbox. We echo the code for debugging and
    # capture any exception tracebacks so the model can see failures.
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
    result = orchestrator.execute(
        session,
        script,
        cwd=session.workspace_path,
        # Do not wrap this command with the sandbox-level `timeout` binary, as
        # some images ship a BusyBox variant with different semantics that
        # prints a noisy "Try `timeout --help`" banner. Long-running snippets
        # should be avoided or guarded in the user code itself.
        timeout_sec=None,
    )

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
