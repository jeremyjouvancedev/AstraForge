from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

import requests
from requests import Response, Session

from deepagents.backends.protocol import BackendProtocol, EditResult, WriteResult
from deepagents.backends.utils import FileInfo, GrepMatch


@dataclass
class _ShellResult:
    exit_code: int
    stdout: str
    stderr: str


class SandboxBackend(BackendProtocol):
    """DeepAgents backend that executes via a remote AstraForge sandbox.

    This mirrors the in-repo `SandboxBackend` but talks to your AstraForge instance
    over HTTP instead of importing Django models directly. It is meant to be used
    from any Python app that wants to construct its own DeepAgent while reusing
    AstraForge's sandbox execution layer.

    Typical usage in a client app:

        from deepagents import create_deep_agent
        from langchain_openai import ChatOpenAI
        from astraforge_sandbox_backend import SandboxBackend

        def backend_factory(rt):
            return SandboxBackend(
                rt,
                base_url=\"https://your-astra-instance.example.com/api\",
                api_key=\"your-api-key\",
                # optional sandbox tuning:
                # session_params={\"image\": \"astraforge/codex-cli:latest\"},
            )

        model = ChatOpenAI(model=\"gpt-4o\", api_key=\"...\")
        agent = create_deep_agent(model=model, backend=backend_factory)
    """

    def __init__(
        self,
        rt,
        *,
        base_url: str,
        api_key: str,
        root_dir: str = "/workspace",
        session_params: Optional[Mapping[str, Any]] = None,
        session_id: Optional[str] = None,
        timeout: Optional[float] = 60.0,
        session: Optional[Session] = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        if not api_key:
            raise ValueError("api_key is required")

        self.rt = rt
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.root_dir = root_dir
        self._session_params: Dict[str, Any] = dict(session_params or {})
        self._timeout = timeout
        self._session_id: Optional[str] = session_id
        self._workspace_root = root_dir
        self._http: Session = session or requests.Session()
        self._http.headers.setdefault("X-Api-Key", self.api_key)

    # internal helpers ------------------------------------------------------

    def _ensure_session_id(self) -> str:
        if self._session_id:
            return self._session_id

        # Allow callers to inject an existing sandbox session via runtime config.
        config = getattr(self.rt, "config", {}) or {}
        if isinstance(config, dict):
            configurable = config.get("configurable") or {}
            if isinstance(configurable, dict):
                session_id = configurable.get("sandbox_session_id")
                if session_id:
                    self._session_id = str(session_id)
                    return self._session_id

        url = f"{self.base_url}/sandbox/sessions/"
        response = self._http.post(url, json=self._session_params, timeout=self._timeout)
        data = self._parse_json(response, expected_status=201)
        try:
            self._session_id = str(data["id"])
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Unexpected sandbox session payload: {data!r}") from exc
        # Align our workspace root with whatever the server reports.
        workspace_path = str(data.get("workspace_path") or self.root_dir)
        self._workspace_root = workspace_path
        self.root_dir = workspace_path
        return self._session_id

    def _abs_path(self, path: str) -> str:
        root = self._workspace_root or "/"
        if not path:
            return root
        if path.startswith("/"):
            return path
        return f"{root.rstrip('/')}/{path.lstrip('/')}"

    def _parse_json(self, response: Response, *, expected_status: int) -> Dict[str, Any]:
        if response.status_code != expected_status:
            detail: Any
            try:
                payload = response.json()
                detail = payload.get("detail") or payload
            except Exception:  # pragma: no cover - best-effort
                detail = response.text
            raise RuntimeError(
                f"Sandbox API call failed ({response.status_code}): {detail!r}"
            )
        try:
            return response.json()  # type: ignore[return-value]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Invalid JSON from sandbox API: {response.text!r}") from exc

    def _shell(self, command: str, cwd: Optional[str] = None) -> _ShellResult:
        session_id = self._ensure_session_id()
        url = f"{self.base_url}/sandbox/sessions/{session_id}/shell/"
        payload: Dict[str, Any] = {"command": command}
        if cwd:
            payload["cwd"] = cwd
        response = self._http.post(url, json=payload, timeout=self._timeout)
        data = self._parse_json(response, expected_status=200)
        exit_code = int(data.get("exit_code", 1) or 0)
        stdout = str(data.get("stdout") or "")
        stderr = str(data.get("stderr") or "")
        return _ShellResult(exit_code=exit_code, stdout=stdout, stderr=stderr)

    def _upload_text(self, target: str, content: str) -> _ShellResult:
        session_id = self._ensure_session_id()
        url = f"{self.base_url}/sandbox/sessions/{session_id}/upload/"
        payload = {
            "path": target,
            "content": content,
            "encoding": "utf-8",
        }
        response = self._http.post(url, json=payload, timeout=self._timeout)
        data = self._parse_json(response, expected_status=200)
        exit_code = int(data.get("exit_code", 1) or 0)
        stdout = str(data.get("stdout") or "")
        stderr = str(data.get("stderr") or "")
        return _ShellResult(exit_code=exit_code, stdout=stdout, stderr=stderr)

    # BackendProtocol implementation ----------------------------------------

    def ls_info(self, path: str) -> List[FileInfo]:
        target = self._abs_path(path or self.root_dir)
        result = self._shell(
            f"ls -la --time-style=+%Y-%m-%dT%H:%M:%SZ {shlex.quote(target)}",
            cwd=None,
        )
        if int(result.exit_code) != 0:
            return []
        stdout = result.stdout or ""
        entries: List[FileInfo] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("total "):
                continue
            parts = line.split(maxsplit=7)
            if len(parts) < 7:
                continue
            perms = parts[0]
            size = parts[4]
            modified = f"{parts[5]}T{parts[6]}" if "T" not in parts[5] else parts[5]
            name = parts[7] if len(parts) > 7 else parts[-1]
            full_path = self._abs_path(name) if target == self.root_dir else f"{target}/{name}"
            try:
                size_val = int(size)
            except ValueError:
                size_val = 0
            entries.append(
                FileInfo(
                    path=full_path,
                    is_dir=perms.startswith("d"),
                    size=size_val,
                    modified_at=modified,
                )
            )
        return entries

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        target = self._abs_path(file_path)
        result = self._shell(f"cat {shlex.quote(target)}")
        if int(result.exit_code) != 0:
            return f"Error: File '{file_path}' not found"
        stdout = result.stdout or ""
        lines = stdout.splitlines()
        if offset < 0:
            offset = 0
        end = offset + limit if limit > 0 else None
        window = lines[offset:end]
        numbered = [f"{i}: {line}" for i, line in enumerate(window, start=offset + 1)]
        return "\n".join(numbered)

    def grep_raw(
        self,
        pattern: str,
        path: Optional[str] = None,
        glob: Optional[str] = None,  # noqa: ARG002 - kept for protocol compatibility
    ) -> List[GrepMatch] | str:
        base = self._abs_path(path or self.root_dir)
        cmd = f"grep -RIn {shlex.quote(pattern)} {shlex.quote(base)}"
        result = self._shell(cmd)
        exit_code = int(result.exit_code)
        stdout = result.stdout or ""
        if exit_code == 2:
            return f"Invalid regex pattern: {pattern}"
        if exit_code not in (0, 1):
            return f"grep error: {stdout.strip()}"
        if not stdout.strip():
            return []
        matches: List[GrepMatch] = []
        for line in stdout.splitlines():
            try:
                path_part, line_part, text = line.split(":", 2)
                lineno = int(line_part)
            except ValueError:
                continue
            matches.append(GrepMatch(path=path_part, line=lineno, text=text))
        return matches

    def glob_info(self, pattern: str, path: str = "/") -> List[FileInfo]:
        base = self._abs_path(path or self.root_dir)
        cmd = f"cd {shlex.quote(base)} && find . -name {shlex.quote(pattern)} -type f"
        result = self._shell(cmd)
        if int(result.exit_code) != 0:
            return []
        stdout = result.stdout or ""
        entries: List[FileInfo] = []
        for line in stdout.splitlines():
            rel = line.strip()
            if not rel:
                continue
            full_path = os.path.normpath(f"{base}/{rel.lstrip('./')}")
            entries.append(FileInfo(path=full_path, is_dir=False))
        return entries

    def write(self, file_path: str, content: str) -> WriteResult:
        target = self._abs_path(file_path)
        # enforce create-only semantics
        check = self._shell(f"test ! -e {shlex.quote(target)}")
        if int(check.exit_code) != 0:
            return WriteResult(error=f"File '{file_path}' already exists")
        result = self._upload_text(target, content)
        if int(result.exit_code) != 0:
            return WriteResult(error=f"Write failed: {result.stdout or result.stderr}")
        return WriteResult(path=file_path, files_update=None)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        raw = self.read(file_path)
        if raw.startswith("Error:"):
            return EditResult(error=raw)
        lines: List[str] = []
        for line in raw.splitlines():
            try:
                _, text = line.split(":", 1)
            except ValueError:
                text = line
            if text.startswith(" "):
                text = text[1:]
            lines.append(text)
        original = "\n".join(lines)
        occurrences = original.count(old_string)
        if occurrences == 0:
            return EditResult(error=f"String '{old_string}' not found in {file_path}")
        if not replace_all and occurrences > 1:
            return EditResult(
                error=(
                    f"String '{old_string}' occurs multiple times in {file_path}; "
                    "set replace_all=True to replace all occurrences"
                )
            )
        if replace_all:
            updated = original.replace(old_string, new_string)
        else:
            updated = original.replace(old_string, new_string, 1)
        target = self._abs_path(file_path)
        result = self._upload_text(target, updated)
        if int(result.exit_code) != 0:
            return EditResult(
                error=f"Edit failed: {result.stdout or result.stderr or 'unknown error'}"
            )
        return EditResult(path=file_path, files_update=None, occurrences=occurrences)

