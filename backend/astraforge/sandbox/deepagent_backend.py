from __future__ import annotations

import os
import shlex
from typing import List, Optional

from deepagents.backends.protocol import BackendProtocol, EditResult, WriteResult
from deepagents.backends.utils import FileInfo, GrepMatch

from astraforge.sandbox.models import SandboxSession
from astraforge.sandbox.services import SandboxOrchestrator, SandboxProvisionError


class SandboxBackend(BackendProtocol):
    """DeepAgents filesystem backend that shells into AstraForge sandboxes.

    The runtime config must provide `configurable.sandbox_session_id`, which
    we use to look up the SandboxSession and execute commands via
    SandboxOrchestrator.
    """

    def __init__(self, rt, root_dir: str = "/workspace") -> None:
        self.rt = rt
        self.root_dir = root_dir
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
            return SandboxSession.objects.get(id=session_id)
        except SandboxSession.DoesNotExist as exc:
            raise RuntimeError(f"Sandbox session {session_id} not found") from exc

    def _abs_path(self, path: str) -> str:
        if not path:
            return self.root_dir
        if path.startswith("/"):
            return path
        return f"{self.root_dir.rstrip('/')}/{path.lstrip('/')}"

    def _shell(self, session: SandboxSession, command: str, cwd: Optional[str] = None):
        try:
            return self.orchestrator.execute(session, command, cwd=cwd)
        except SandboxProvisionError as exc:
            raise RuntimeError(str(exc)) from exc

    # BackendProtocol implementation ---------------------------------------

    def ls_info(self, path: str) -> List[FileInfo]:
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
        return entries

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        session = self._session()
        target = self._abs_path(file_path)
        result = self._shell(session, f"cat {shlex.quote(target)}")
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
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        session = self._session()
        base = self._abs_path(path or self.root_dir)
        cmd = f"grep -RIn {shlex.quote(pattern)} {shlex.quote(base)}"
        result = self._shell(session, cmd)
        exit_code = int(result.exit_code)
        stdout = result.stdout or ""
        if exit_code == 2:
            return f"Invalid regex pattern: {pattern}"
        if exit_code not in (0, 1):
            return f"grep error: {stdout.strip()}"
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
        session = self._session()
        base = self._abs_path(path or self.root_dir)
        cmd = f"cd {shlex.quote(base)} && find . -name {shlex.quote(pattern)} -type f"
        result = self._shell(session, cmd)
        if int(result.exit_code) != 0:
            return []
        stdout = result.stdout or ""
        entries: list[FileInfo] = []
        for line in stdout.splitlines():
            rel = line.strip()
            if not rel:
                continue
            full_path = os.path.normpath(f"{base}/{rel.lstrip('./')}")
            entries.append(FileInfo(path=full_path, is_dir=False))
        return entries

    def write(self, file_path: str, content: str) -> WriteResult:
        session = self._session()
        target = self._abs_path(file_path)
        # enforce create-only semantics
        check = self._shell(session, f"test ! -e {shlex.quote(target)}")
        if int(check.exit_code) != 0:
            return WriteResult(error=f"File '{file_path}' already exists")
        result = self.orchestrator.upload_bytes(session, target, content.encode("utf-8"))
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
        lines = []
        for line in raw.splitlines():
            try:
                _, text = line.split(":", 1)
            except ValueError:
                text = line
            # Drop the single space added after the line number in read(),
            # but preserve all original indentation that follows.
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
        # Overwrite existing file contents directly; edits by definition target existing files.
        session = self._session()
        target = self._abs_path(file_path)
        result = self.orchestrator.upload_bytes(session, target, updated.encode("utf-8"))
        if int(result.exit_code) != 0:
            return EditResult(
                error=f"Edit failed: {result.stdout or result.stderr or 'unknown error'}"
            )
        return EditResult(path=file_path, files_update=None, occurrences=occurrences)
