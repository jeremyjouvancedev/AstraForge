from __future__ import annotations

import json
import logging
import os
import re
import shlex
from typing import Any, List, Mapping, Optional
from deepagents.backends.protocol import BackendProtocol, EditResult, WriteResult
from deepagents.backends.utils import (
    FileInfo,
    GrepMatch,
    check_empty_content,
    format_content_with_line_numbers,
    perform_string_replacement,
)

from astraforge.sandbox.models import SandboxSession, SandboxSnapshot
from astraforge.sandbox.services import SandboxOrchestrator, SandboxProvisionError

try:
    # Optional HTTP backend from the standalone package. When installed and
    # configured via environment variables, this lets SandboxBackend talk to a
    # remote AstraForge instance over HTTP instead of the local Django ORM.
    from astraforge_sandbox_backend import SandboxBackend as HttpSandboxBackend
except Exception:  # noqa: BLE001
    HttpSandboxBackend = None


class _SandboxBackend(BackendProtocol):
    """DeepAgents filesystem backend that shells into AstraForge sandboxes.

    This class supports two execution modes:

    - **Internal mode** (default): uses the local Django `SandboxSession` model and
      `SandboxOrchestrator` to shell directly into sandboxes provisioned by this
      backend. The runtime config must provide `configurable.sandbox_session_id`.
    - **HTTP mode** (optional): when the `AstraForgeSandboxBackend` package is
      installed *and* sandbox API credentials are provided (see below), this class
      delegates to the HTTP client backend so all filesystem operations are
      executed via a remote AstraForge instance.

    HTTP mode is enabled when either constructor arguments or environment variables
    provide both:

    - `base_url` / `ASTRA_FORGE_API_URL`
    - `api_key` / `ASTRA_FORGE_API_KEY`

    If those are missing, or the external package is not installed, the backend
    automatically falls back to internal mode.
    """

    def __init__(
        self,
        rt,
        root_dir: str = "/workspace",
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        session_params: Mapping[str, Any] | None = None,
        debug: bool | None = None,
    ) -> None:
        self.rt = rt
        self.root_dir = root_dir
        self._workspace_root = root_dir

        # Resolve optional HTTP configuration from args or environment.
        base_url = base_url or os.getenv("ASTRA_FORGE_API_URL")
        api_key = api_key or os.getenv("ASTRA_FORGE_API_KEY")
        debug_env = os.getenv("ASTRA_FORGE_SANDBOX_DEBUG", "0").lower()
        self._debug = debug if debug is not None else debug_env in {"1", "true", "yes"}
        self._log = logging.getLogger(__name__)

        self._http_backend: Optional[BackendProtocol]
        if HttpSandboxBackend is not None and base_url and api_key:
            # HTTP mode: delegate to the external backend implementation.
            self._http_backend = HttpSandboxBackend(
                rt,
                base_url=base_url,
                api_key=api_key,
                root_dir=root_dir,
                session_params=session_params,
            )
            self.orchestrator: Optional[SandboxOrchestrator] = None
        else:
            # Internal mode: use local Django models + orchestrator.
            self._http_backend = None
            self.orchestrator = SandboxOrchestrator()

    # helpers ---------------------------------------------------------------

    def _session(self) -> SandboxSession:
        config = getattr(self.rt, "config", {}) or {}
        if not isinstance(config, dict):
            raise RuntimeError("Sandbox backend requires dict-like runtime config")
        configurable = config.get("configurable") or {}
        if not isinstance(configurable, dict):
            raise RuntimeError("Sandbox backend requires configurable dict in runtime config")
        session_id = configurable.get("sandbox_session_id")
        if not session_id:
            raise RuntimeError("sandbox_session_id missing from runtime config")
        try:
            session = SandboxSession.objects.get(id=session_id)
        except SandboxSession.DoesNotExist as exc:
            raise RuntimeError(f"Sandbox session {session_id} not found") from exc

        session = self._ensure_ready(session)
        # Mirror the HTTP backend: align root to the session's workspace path.
        self._workspace_root = session.workspace_path or self.root_dir
        return session

    def _abs_path(self, path: str) -> str:
        base = self._workspace_root or self.root_dir
        if not path:
            return base
        if path.startswith("/"):
            return path
        return f"{base.rstrip('/')}/{path.lstrip('/')}"

    def _shell(self, session: SandboxSession, command: str, cwd: Optional[str] = None):
        try:
            return self.orchestrator.execute(session, command, cwd=cwd)
        except SandboxProvisionError as exc:
            raise RuntimeError(str(exc)) from exc

    def _log_llm_error(self, message: str) -> None:
        try:
            self._log.error("backend response to llm: %s", message)
        except Exception:
            pass

    def _ensure_ready(self, session: SandboxSession) -> SandboxSession:
        """Provision and restore a session if it is not currently ready."""
        if session.status == SandboxSession.Status.READY:
            return session

        try:
            self.orchestrator.provision(session)
        except SandboxProvisionError as exc:
            raise RuntimeError(f"Sandbox auto-provision failed: {exc}") from exc

        metadata = session.metadata or {}
        latest_snapshot_id = metadata.get("latest_snapshot_id")
        if latest_snapshot_id:
            snapshot = (
                SandboxSnapshot.objects.filter(id=latest_snapshot_id, session=session).first()
            )
            if snapshot:
                try:
                    self.orchestrator.restore_snapshot(session, snapshot)
                except SandboxProvisionError as exc:  # pragma: no cover - surfaced upstream
                    raise RuntimeError(f"Snapshot restore failed: {exc}") from exc

        # Refresh workspace root in case provision/restore updated it.
        self._workspace_root = session.workspace_path or self.root_dir
        return session

    # BackendProtocol implementation ---------------------------------------

    def ls_info(self, path: str) -> List[FileInfo]:
        if self._http_backend is not None:
            return self._http_backend.ls_info(path)

        session = self._session()
        target = self._abs_path(path or self.root_dir)
        result = self._shell(
            session,
            f"ls -la --time-style=+%Y-%m-%dT%H:%M:%SZ {shlex.quote(target)}",
            cwd=None,
        )
        if int(result.exit_code) != 0:
            return []
        stdout = result.stdout or ""
        entries: list[FileInfo] = []
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
        entries.sort(key=lambda item: item.get("path", ""))
        return entries

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        if self._http_backend is not None:
            return self._http_backend.read(file_path, offset=offset, limit=limit)

        session = self._session()
        target = self._abs_path(file_path)
        result = self._shell(session, f"cat {shlex.quote(target)}")
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

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        if self._http_backend is not None:
            return self._http_backend.grep_raw(pattern, path=path, glob=glob)

        try:
            re.compile(pattern)
        except re.error as exc:
            msg = f"Invalid regex pattern: {exc}"
            self._log_llm_error(msg)
            return msg

        session = self._session()
        base = self._abs_path(path or self.root_dir)

        rg_matches = self._ripgrep_search(session, pattern, base, glob)
        if rg_matches is not None:
            return rg_matches

        return self._grep_fallback(session, pattern, base, glob)

    def _ripgrep_search(
        self,
        session: SandboxSession,
        pattern: str,
        base: str,
        glob: str | None,
    ) -> list[GrepMatch] | None:
        parts = ["rg", "--json"]
        if glob:
            parts.extend(["--glob", glob])
        parts.extend(["--", pattern, base])
        cmd = " ".join(shlex.quote(p) for p in parts)
        result = self._shell(session, cmd)
        if int(result.exit_code) not in (0, 1):
            return None

        matches: list[GrepMatch] = []
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
        self,
        session: SandboxSession,
        pattern: str,
        base: str,
        glob: str | None,
    ) -> list[GrepMatch] | str:
        parts = ["grep", "-RIn"]
        if glob:
            parts.append(f"--include={glob}")
        parts.extend([pattern, base])
        cmd = " ".join(shlex.quote(p) for p in parts)
        result = self._shell(session, cmd)
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
        matches: list[GrepMatch] = []
        for line in stdout.splitlines():
            try:
                path_part, line_part, text = line.split(":", 2)
                lineno = int(line_part)
            except ValueError:
                continue
            matches.append(GrepMatch(path=path_part, line=lineno, text=text))
        return matches

    def glob_info(self, pattern: str, path: str = "/") -> List[FileInfo]:
        if self._http_backend is not None:
            return self._http_backend.glob_info(pattern, path=path)

        session = self._session()
        base = self._abs_path(path or self.root_dir)
        search_pattern = pattern.lstrip("/") if pattern.startswith("/") else pattern
        cmd = f"""python - <<'PY'
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
        result = self._shell(session, cmd)
        if int(result.exit_code) != 0:
            return []
        try:
            parsed = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            return []
        return [FileInfo(**item) for item in parsed if isinstance(item, dict)]

    def write(self, file_path: str, content: str) -> WriteResult:
        if self._http_backend is not None:
            return self._http_backend.write(file_path, content)

        session = self._session()
        target = self._abs_path(file_path)
        # enforce create-only semantics
        check = self._shell(session, f"test ! -e {shlex.quote(target)}")
        if int(check.exit_code) != 0:
            error = (
                f"Cannot write to {file_path} because it already exists. "
                "Read and then make an edit, or write to a new path."
            )
            self._log_llm_error(error)
            return WriteResult(error=error)
        result = self.orchestrator.upload_bytes(session, target, content.encode("utf-8"))
        exit_code = int(result.exit_code)
        if exit_code != 0:
            base_msg = result.stdout or result.stderr or ""
            message = base_msg or f"Write failed with exit code {exit_code}"
            if self._debug:
                self._log.debug(
                    "sandbox write failed: path=%s exit=%s stderr=%r stdout=%r",
                    target,
                    exit_code,
                    result.stderr,
                    (result.stdout or "").strip(),
                )
            return WriteResult(error=message)
        return WriteResult(path=target, files_update=None)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        if self._http_backend is not None:
            return self._http_backend.edit(
                file_path,
                old_string,
                new_string,
                replace_all=replace_all,
            )

        target = self._abs_path(file_path)
        session = self._session()
        raw = self._shell(session, f"cat {shlex.quote(target)}")
        if int(raw.exit_code) != 0:
            return EditResult(error=f"Error: File '{file_path}' not found")

        replacement = perform_string_replacement(
            raw.stdout or "", old_string, new_string, replace_all
        )
        if isinstance(replacement, str):
            return EditResult(error=replacement)
        updated, occurrences = replacement

        # Overwrite existing file contents directly; edits by definition target existing files.
        result = self.orchestrator.upload_bytes(session, target, updated.encode("utf-8"))
        if int(result.exit_code) != 0:
            message = result.stdout or result.stderr or "unknown error"
            self._log_llm_error(f"Edit failed: {message}")
            return EditResult(error=f"Edit failed: {message}")
        return EditResult(path=target, files_update=None, occurrences=int(occurrences))


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
    ) -> list[GrepMatch] | str:
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
        root_dir: str = "/workspace",
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        session_params: Mapping[str, Any] | None = None,
        debug: bool | None = None,
        allowed_root: str | None = "/workspace",
    ) -> None:
        impl = _SandboxBackend(
            rt,
            root_dir=root_dir,
            base_url=base_url,
            api_key=api_key,
            session_params=session_params,
            debug=debug,
        )
        super().__init__(impl, allowed_root=allowed_root or "/workspace")
