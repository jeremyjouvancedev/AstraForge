"""Domain-level workspace abstractions describing ephemeral execution environments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(slots=True)
class WorkspaceContext:
    """Represents a provisioned workspace capable of running Codex CLI."""

    ref: str
    mode: str
    repository: str
    branch: str
    path: str
    proxy_url: str | None = None
    metadata: Dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        payload = {
            "ref": self.ref,
            "mode": self.mode,
            "repository": self.repository,
            "branch": self.branch,
            "path": self.path,
        }
        if self.proxy_url:
            payload["proxy_url"] = self.proxy_url
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


@dataclass(slots=True)
class CommandResult:
    """Outcome of a command executed inside a workspace."""

    exit_code: int
    stdout: str
    stderr: str


@dataclass(slots=True)
class ExecutionOutcome:
    """Result emitted after Codex CLI finishes applying changes."""

    diff: str
    reports: Dict[str, object] = field(default_factory=dict)
    artifacts: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        payload = {
            "diff": self.diff,
            "reports": self.reports,
        }
        if self.artifacts:
            payload["artifacts"] = self.artifacts
        return payload
