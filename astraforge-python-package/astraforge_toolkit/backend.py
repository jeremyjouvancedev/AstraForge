from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import requests
from requests import Response, Session

from deepagents.backends.protocol import BackendProtocol, EditResult, WriteResult
from deepagents.backends.utils import (
    FileInfo,
    GrepMatch,
    check_empty_content,
    format_content_with_line_numbers,
    perform_string_replacement,
)


@dataclass
class _ShellResult:
    exit_code: int
    stdout: str
    stderr: str


def _env_flag(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "on"}


class _SandboxBackend(BackendProtocol):
    """DeepAgents backend that executes via a remote AstraForge sandbox API.

    This mirrors the in-repo `SandboxBackend` but talks to a remote AstraForge instance
    over HTTP. Use it when constructing your own DeepAgent runtime outside of the
    Django app.
    """

    def __init__(
        self,
        rt,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        root_dir: str = "/workspace",
        session_params: Optional[Mapping[str, Any]] = None,
        session_id: Optional[str] = None,
        timeout: Optional[float] = 60.0,
        session: Optional[Session] = None,
        debug: Optional[bool] = None,
    ) -> None:
        # Mirror backend logic: allow env overrides so callers can omit args.
        base_url = base_url or os.getenv("ASTRA_FORGE_API_URL")
        api_key = api_key or os.getenv("ASTRA_FORGE_API_KEY")
        if not base_url:
            raise ValueError("base_url is required (or set ASTRA_FORGE_API_URL)")
        if not api_key:
            raise ValueError("api_key is required (or set ASTRA_FORGE_API_KEY)")

        debug_env = os.getenv("ASTRA_FORGE_SANDBOX_DEBUG", "0").lower()
        self._debug = debug if debug is not None else debug_env in {"1", "true", "yes"}
        self._log = logging.getLogger(__name__)

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

        return self._start_session()

    def _abs_path(self, path: str) -> str:
        root = self._workspace_root or "/"
        if not path:
            return root
        if path.startswith("/"):
            return path
        return f"{root.rstrip('/')}/{path.lstrip('/')}"

    def _parse_json(
        self, response: Response, *, expected_status: int
    ) -> Dict[str, Any]:
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
            raise RuntimeError(
                f"Invalid JSON from sandbox API: {response.text!r}"
            ) from exc

    def _shell(self, command: str, cwd: Optional[str] = None) -> _ShellResult:
        session_id = self._ensure_session_ready()
        url = f"{self.base_url}/sandbox/sessions/{session_id}/shell/"
        payload: Dict[str, Any] = {"command": command}
        if cwd:
            payload["cwd"] = cwd
        response = self._http.post(url, json=payload, timeout=self._timeout)
        data = self._parse_json(response, expected_status=200)
        exit_code = int(data.get("exit_code", 1) or 0)
        stdout = str(data.get("stdout") or "")
        stderr = str(data.get("stderr") or "")
        if self._debug:
            self._log.debug(
                "sandbox shell",
                extra={"command": command, "cwd": cwd, "exit_code": exit_code},
            )
        return _ShellResult(exit_code=exit_code, stdout=stdout, stderr=stderr)

    def _upload_text(self, target: str, content: str) -> _ShellResult:
        session_id = self._ensure_session_ready()
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

    def _start_session(self, restore_snapshot_id: Optional[str] = None) -> str:
        payload: Dict[str, Any] = dict(self._session_params)
        if restore_snapshot_id:
            payload["restore_snapshot_id"] = restore_snapshot_id
        url = f"{self.base_url}/sandbox/sessions/"
        response = self._http.post(url, json=payload, timeout=self._timeout)
        data = self._parse_json(response, expected_status=201)
        try:
            self._session_id = str(data["id"])
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Unexpected sandbox session payload: {data!r}") from exc
        workspace_path = str(data.get("workspace_path") or self.root_dir)
        self._workspace_root = workspace_path
        self.root_dir = workspace_path
        return self._session_id

    def _get_session(self, session_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/sandbox/sessions/{session_id}/"
        response = self._http.get(url, timeout=self._timeout)
        return self._parse_json(response, expected_status=200)

    def _ensure_session_ready(self) -> str:
        session_id = self._ensure_session_id()
        try:
            data = self._get_session(session_id)
        except RuntimeError:
            # If we cannot fetch the session, try creating a new one.
            return self._start_session()

        status_value = str(data.get("status") or "").lower()
        workspace_path = str(data.get("workspace_path") or self.root_dir)
        metadata = data.get("metadata") or {}
        latest_snapshot_id = (
            metadata.get("latest_snapshot_id") if isinstance(metadata, dict) else None
        )

        if status_value == "ready":
            self._workspace_root = workspace_path
            self.root_dir = workspace_path
            return session_id

        # Session not ready: create a new one and restore from the latest snapshot if present.
        return self._start_session(restore_snapshot_id=str(latest_snapshot_id) if latest_snapshot_id else None)

    def _log_llm_error(self, message: str) -> None:
        try:
            self._log.error("backend response to llm: %s", message)
        except Exception:
            pass

    # BackendProtocol implementation ----------------------------------------

    def ls_info(self, path: str) -> List[FileInfo]:
        """List files and directories in the specified directory (non-recursive).

        Args:
            path: Absolute path to directory.

        Returns:
            List of FileInfo-like dicts for files and directories directly in the directory.
            Directories have a trailing / in their path and is_dir=True.
        """
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
            full_path = (
                self._abs_path(name) if target == self.root_dir else f"{target}/{name}"
            )
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
        entries.sort(key=lambda item: item.get("path", ""))
        return entries

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        """Read file content with line numbers.

        Args:
            file_path: Absolute file path
            offset: Line offset to start reading from (0-indexed)
            limit: Maximum number of lines to readReturns:
            Formatted file content with line numbers, or error message.
        """
        target = self._abs_path(file_path)
        result = self._shell(f"cat {shlex.quote(target)}")
        if int(result.exit_code) != 0:
            msg = f"Error: File '{file_path}' not found"
            self._log_llm_error(msg)
            return msg
        content = result.stdout or ""
        empty_msg = check_empty_content(content)
        if empty_msg:
            return empty_msg

        lines = content.splitlines()
        start_idx = offset if offset > 0 else 0
        end_idx = min(start_idx + limit, len(lines))

        if start_idx >= len(lines):
            msg = f"Error: Line offset {offset} exceeds file length ({len(lines)} lines)"
            self._log_llm_error(msg)
            return msg

        selected = lines[start_idx:end_idx]
        return format_content_with_line_numbers(selected, start_line=start_idx + 1)

    def write(self, file_path: str, content: str) -> WriteResult:
        """Create a new file with content.
        Returns WriteResult with files_update to update LangGraph state.
        """
        target = self._abs_path(file_path)
        # create-only semantics for parity with the in-app backend
        exists_check = self._shell(f"test ! -e {shlex.quote(target)}")
        if int(exists_check.exit_code) != 0:
            error = (
                f"Cannot write to {file_path} because it already exists. "
                "Read and then make an edit, or write to a new path."
            )
            self._log_llm_error(error)
            return WriteResult(error=error)

        result = self._upload_text(target, content)
        exit_code = int(result.exit_code)
        if exit_code != 0:
            message = result.stderr or f"Write failed with exit code {exit_code}"
            if self._debug:
                stdout = (result.stdout or "").strip()
                self._log.debug(
                    "sandbox write failed: path=%s exit=%s stderr=%r stdout=%r",
                    target,
                    exit_code,
                    result.stderr,
                    stdout,
                )
            self._log_llm_error(message)
            return WriteResult(error=message)
        return WriteResult(path=target, files_update=None)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Edit a file by replacing string occurrences.
        Returns EditResult with files_update and occurrences.
        """
        target = self._abs_path(file_path)
        raw_result = self._shell(f"cat {shlex.quote(target)}")
        if int(raw_result.exit_code) != 0:
            msg = f"Error: File '{file_path}' not found"
            self._log_llm_error(msg)
            return EditResult(error=msg)

        replacement = perform_string_replacement(
            raw_result.stdout or "", old_string, new_string, replace_all
        )
        if isinstance(replacement, str):
            self._log_llm_error(replacement)
            return EditResult(error=replacement)
        updated, occurrences = replacement

        result = self._upload_text(target, updated)
        exit_code = int(result.exit_code)
        if exit_code != 0:
            message = result.stderr or f"Edit failed with exit code {exit_code}"
            if self._debug:
                stdout = (result.stdout or "").strip()
                self._log.debug(
                    "sandbox edit failed: path=%s exit=%s stderr=%r stdout=%r",
                    target,
                    exit_code,
                    result.stderr,
                    stdout,
                )
            self._log_llm_error(message)
            return EditResult(error=message)
        return EditResult(path=target, files_update=None, occurrences=int(occurrences))

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> List[GrepMatch] | str:
        try:
            re.compile(pattern)
        except re.error as exc:
            msg = f"Invalid regex pattern: {exc}"
            self._log_llm_error(msg)
            return msg

        base = self._abs_path(path or self.root_dir)

        rg_matches = self._ripgrep_search(pattern, base, glob)
        if rg_matches is not None:
            return rg_matches

        return self._grep_fallback(pattern, base, glob)

    def _ripgrep_search(
        self, pattern: str, base: str, glob: str | None
    ) -> List[GrepMatch] | None:
        parts = ["rg", "--json"]
        if glob:
            parts.extend(["--glob", glob])
        parts.extend(["--", pattern, base])
        command = " ".join(shlex.quote(p) for p in parts)
        result = self._shell(command)
        if int(result.exit_code) not in (0, 1):
            return None

        matches: List[GrepMatch] = []
        for line in (result.stdout or "").splitlines():
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get("type") != "match":
                continue
            pdata = data.get("data", {})
            ftext = pdata.get("path", {}).get("text")
            line_no = pdata.get("line_number")
            text = (pdata.get("lines", {}) or {}).get("text", "").rstrip("\n")
            if not ftext or line_no is None:
                continue
            matches.append(GrepMatch(path=ftext, line=int(line_no), text=text))
        return matches

    def _grep_fallback(
        self, pattern: str, base: str, glob: str | None
    ) -> List[GrepMatch] | str:
        parts = ["grep", "-RIn"]
        if glob:
            parts.append(f"--include={glob}")
        parts.extend([pattern, base])
        command = " ".join(shlex.quote(p) for p in parts)
        result = self._shell(command)
        exit_code = int(result.exit_code)
        stdout = result.stdout or ""
        if exit_code == 2:
            msg = f"Invalid regex pattern: {pattern}"
            self._log_llm_error(msg)
            return msg
        if exit_code not in (0, 1):
            msg = f"grep error: {stdout.strip()}"
            self._log_llm_error(msg)
            return msg
        if not stdout.strip():
            return []

        matches: List[GrepMatch] = []
        for line in stdout.splitlines():
            try:
                file_path, line_no, text = line.split(":", 2)
            except ValueError:
                continue
            try:
                lineno_int = int(line_no)
            except ValueError:
                continue
            matches.append(GrepMatch(path=file_path, line=lineno_int, text=text))
        return matches

    def glob_info(self, pattern: str, path: str = "/") -> List[FileInfo]:
        search_pattern = pattern.lstrip("/") if pattern.startswith("/") else pattern
        base = self._abs_path(path or self.root_dir)
        command = f"""python - <<'PY'
import json
from datetime import datetime
from pathlib import Path

base = Path({base!r})
pattern = {search_pattern!r}

if not base.exists() or not base.is_dir():
    print("[]")
    raise SystemExit(0)

results = []
for matched in base.rglob(pattern):
    try:
        is_file = matched.is_file()
    except OSError:
        continue
    if not is_file:
        continue
    try:
        st = matched.stat()
        results.append({{
            "path": str(matched),
            "is_dir": False,
            "size": int(st.st_size),
            "modified_at": datetime.fromtimestamp(st.st_mtime).isoformat(),
        }})
    except OSError:
        results.append({{"path": str(matched), "is_dir": False}})

results.sort(key=lambda item: item.get("path", ""))
print(json.dumps(results))
PY"""
        result = self._shell(command)
        if int(result.exit_code) != 0:
            return []
        try:
            parsed = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            return []
        return [FileInfo(**item) for item in parsed if isinstance(item, dict)]

    def python_exec(self, code: str, timeout: Optional[int] = 30) -> str:
        command = f"python - <<'PYCODE'\n{code}\nPYCODE"
        result = self._shell(command)
        if int(result.exit_code) != 0:
            return (
                result.stderr
                or f"Error executing Python code (exit {result.exit_code})"
            )
        return result.stdout or ""

    def shell(
        self, command: str, cwd: Optional[str] = None, timeout: Optional[int] = 30
    ) -> str:
        result = self._shell(command, cwd=cwd)
        if int(result.exit_code) != 0:
            return result.stderr or f"Command failed with exit code {result.exit_code}"
        return result.stdout or ""

    def download(self, path: str) -> bytes:
        target = self._abs_path(path)
        session_id = self._ensure_session_id()
        url = f"{self.base_url}/sandbox/sessions/{session_id}/files/content/"
        response = self._http.get(url, params={"path": target}, timeout=self._timeout)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to download {path}: {response.status_code}")
        return response.content


class PolicyWrapper(BackendProtocol):
    """Backend wrapper that enforces an allowed workspace root."""

    def __init__(self, inner: BackendProtocol, allowed_root: str = "/workspace") -> None:
        self.inner = inner
        self.allowed_root = allowed_root.rstrip("/") or "/"
        self._prefix = (
            self.allowed_root if self.allowed_root == "/" else self.allowed_root + "/"
        )
        self._log = logging.getLogger(__name__)

    def _normalize(self, path: str | None) -> str:
        if not path or path == "/":
            return self.allowed_root
        if path.startswith("/"):
            return path
        return f"{self._prefix}{path.lstrip('/')}"

    def _deny(self, path: str | None) -> bool:
        normalized = self._normalize(path)
        return not (
            normalized == self.allowed_root or normalized.startswith(self._prefix)
        )

    def _error(self, path: str | None) -> str:
        display = path or "."
        msg = f"Path '{display}' is outside allowed root {self.allowed_root}"
        try:
            self._log.error("backend response to llm: %s", msg)
        except Exception:
            pass
        return msg

    def ls_info(self, path: str) -> List[FileInfo]:
        if self._deny(path):
            return []
        return self.inner.ls_info(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        if self._deny(file_path):
            return self._error(file_path)
        return self.inner.read(file_path, offset=offset, limit=limit)

    def grep_raw(
        self, pattern: str, path: str | None = None, glob: str | None = None
    ) -> List[GrepMatch] | str:
        if self._deny(path):
            return self._error(path)
        return self.inner.grep_raw(pattern, path, glob)

    def glob_info(self, pattern: str, path: str = "/") -> List[FileInfo]:
        if self._deny(path):
            return []
        return self.inner.glob_info(pattern, path)

    def write(self, file_path: str, content: str) -> WriteResult:
        if self._deny(file_path):
            return WriteResult(error=self._error(file_path))
        return self.inner.write(file_path, content)

    def edit(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> EditResult:
        if self._deny(file_path):
            return EditResult(error=self._error(file_path))
        return self.inner.edit(file_path, old_string, new_string, replace_all)

    def __getattr__(self, name: str):
        # Delegate attribute access to the inner backend for compatibility.
        return getattr(self.inner, name)


class SandboxBackend(PolicyWrapper):
    """Policy-enforced sandbox backend. Uses PolicyWrapper by default."""

    def __init__(
        self,
        rt,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        root_dir: str = "/workspace",
        session_params: Optional[Mapping[str, Any]] = None,
        session_id: Optional[str] = None,
        timeout: Optional[float] = 60.0,
        session: Optional[Session] = None,
        debug: Optional[bool] = None,
        allowed_root: Optional[str] = "/workspace",
    ) -> None:
        impl = _SandboxBackend(
            rt,
            base_url=base_url,
            api_key=api_key,
            root_dir=root_dir,
            session_params=session_params,
            session_id=session_id,
            timeout=timeout,
            session=session,
            debug=debug,
        )
        super().__init__(impl, allowed_root=allowed_root or "/workspace")
