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
    """DeepAgents backend that executes via a remote AstraForge sandbox API.

    This mirrors the in-repo `SandboxBackend` but talks to a remote AstraForge instance
    over HTTP. Use it when constructing your own DeepAgent runtime outside of the
    Django app.
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
            except Exception:  # pragma: no cover
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
        content = result.stdout or ""
        if offset or limit:
            content = content[offset : offset + limit]
        return content

    def write(self, file_path: str, content: str) -> WriteResult:
        target = self._abs_path(file_path)
        result = self._upload_text(target, content)
        ok = int(result.exit_code) == 0
        return WriteResult(path=target, success=ok, error=result.stderr or None)

    def edit(self, file_path: str, edits: List[str]) -> EditResult:
        target = self._abs_path(file_path)
        content = "\n".join(edits)
        result = self._upload_text(target, content)
        ok = int(result.exit_code) == 0
        return EditResult(path=target, success=ok, error=result.stderr or None)

    def grep(self, pattern: str, path: str, max_count: int = 50) -> List[GrepMatch]:
        target = self._abs_path(path or self.root_dir)
        command = f"grep -R -n -m {max_count} {shlex.quote(pattern)} {shlex.quote(target)}"
        result = self._shell(command)
        if int(result.exit_code) != 0:
            return []
        matches: List[GrepMatch] = []
        for line in (result.stdout or "").splitlines():
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            file_path, line_no, snippet = parts[0], parts[1], parts[2]
            matches.append(GrepMatch(path=file_path, line=int(line_no or 0), match=snippet))
        return matches

    def python_exec(self, code: str, timeout: Optional[int] = 30) -> str:
        command = f"python - <<'PYCODE'\n{code}\nPYCODE"
        result = self._shell(command)
        if int(result.exit_code) != 0:
            return result.stderr or f"Error executing Python code (exit {result.exit_code})"
        return result.stdout or ""

    def shell(self, command: str, cwd: Optional[str] = None, timeout: Optional[int] = 30) -> str:
        result = self._shell(command, cwd=cwd)
        if int(result.exit_code) != 0:
            return result.stderr or f"Command failed with exit code {result.exit_code}"
        return result.stdout or ""

    def download(self, path: str) -> bytes:
        target = self._abs_path(path)
        session_id = self._ensure_session_id()
        url = f"{self.base_url}/sandbox/sessions/{session_id}/files/content"
        response = self._http.get(url, params={"path": target}, timeout=self._timeout)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to download {path}: {response.status_code}")
        return response.content
