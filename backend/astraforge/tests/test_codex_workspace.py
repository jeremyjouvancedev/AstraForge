"""Tests for Codex workspace operator helpers."""

from __future__ import annotations

import subprocess

from astraforge.domain.models.workspace import CommandResult, WorkspaceContext
from astraforge.infrastructure.workspaces.codex import CodexWorkspaceOperator


class _DummyProvisioner:
    def spawn(self, repo: str, toolchain: str) -> str:  # pragma: no cover - test stub
        raise NotImplementedError

    def cleanup(self, ref: str) -> None:  # pragma: no cover - test stub
        raise NotImplementedError


class _StubRunner:
    def __init__(self, result: CommandResult) -> None:
        self._result = result
        self.last_command = None
        self.last_allow_failure = None
        self.commands: list[list[str]] = []

    def run(
        self,
        command,
        *,
        cwd=None,
        env=None,
        stream=None,
        allow_failure=False,
    ) -> CommandResult:
        rendered = list(command)
        self.last_command = rendered
        self.commands.append(rendered)
        self.last_allow_failure = allow_failure
        return self._result


def test_collect_results_skips_diff_when_workspace_not_git_repo():
    events: list[dict[str, str]] = []

    def stream(event: dict[str, str]) -> None:
        events.append(event)

    runner = _StubRunner(
        CommandResult(
            exit_code=128,
            stdout="fatal: Not a git repository (or any of the parent directories): .git\n",
            stderr="",
        )
    )
    operator = CodexWorkspaceOperator(provisioner=_DummyProvisioner(), runner=runner)
    workspace = WorkspaceContext(
        ref="docker://codex-123",
        mode="docker",
        repository="example/repo",
        branch="main",
        path="/workspace",
    )

    outcome = operator._collect_results(workspace, stream=stream)

    assert outcome.diff == ""
    assert events[-1]["stage"] == "diff"
    assert events[-1]["message"] == "Git repository not detected in workspace; skipping diff"
    assert runner.last_allow_failure is True


class _FallbackRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(
        self,
        command,
        *,
        cwd=None,
        env=None,
        stream=None,
        allow_failure=False,
    ) -> CommandResult:
        rendered = list(command)
        self.commands.append(rendered)
        if "--pull" in rendered:
            raise subprocess.CalledProcessError(125, rendered, output="")
        return CommandResult(exit_code=0, stdout="", stderr="")


def test_bootstrap_builds_local_image_when_registry_denies(monkeypatch, tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    monkeypatch.setenv("CODEX_CLI_BUILD_CONTEXT", str(tmp_path))
    events: list[dict[str, str]] = []

    def stream(event: dict[str, str]) -> None:
        events.append(event)

    runner = _FallbackRunner()
    operator = CodexWorkspaceOperator(provisioner=_DummyProvisioner(), runner=runner)

    operator._bootstrap_docker_container("codex-123", "astraforge/codex-cli:latest", stream)

    assert any("--pull" in cmd for cmd in runner.commands)
    assert any(cmd[:3] == ["docker", "build", "-t"] for cmd in runner.commands)
    assert any(
        cmd[:5] == ["docker", "run", "-d", "--name", "codex-123"] and "--pull" not in cmd
        for cmd in runner.commands
    )
    assert any(
        event.get("message", "").startswith("Image astraforge/codex-cli:latest unavailable")
        for event in events
    )
