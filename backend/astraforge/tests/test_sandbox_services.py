from __future__ import annotations

import subprocess

import pytest
from django.contrib.auth import get_user_model

from astraforge.domain.models.workspace import CommandResult
from astraforge.sandbox.models import SandboxSession
from astraforge.sandbox.services import SandboxOrchestrator, SandboxProvisionError

pytestmark = pytest.mark.django_db


class _RunnerConflictThenSuccess:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.failed_once = False

    def run(self, command, *, cwd=None, env=None, stream=None, allow_failure=False):
        rendered = list(command)
        self.calls.append(rendered)
        if rendered[:3] == ["docker", "run", "-d"] and not self.failed_once:
            self.failed_once = True
            raise subprocess.CalledProcessError(
                125,
                rendered,
                output="docker: Error response from daemon: Conflict. The container name is already in use.",
            )
        return CommandResult(exit_code=0, stdout="", stderr="")


def _create_session(user, **overrides) -> SandboxSession:
    defaults = {
        "mode": SandboxSession.Mode.DOCKER,
        "image": "astraforge/codex-cli:latest",
        "status": SandboxSession.Status.READY,
        "ref": "",
        "control_endpoint": "",
        "workspace_path": "/workspace",
        "idle_timeout_sec": 60,
        "max_lifetime_sec": 3600,
    }
    defaults.update(overrides)
    return SandboxSession.objects.create(user=user, **defaults)


def test_spawn_docker_retries_on_conflict():
    user = get_user_model().objects.create_user(username="runner", password="pass12345")
    session = _create_session(user)
    runner = _RunnerConflictThenSuccess()
    orchestrator = SandboxOrchestrator(runner=runner)

    runtime = orchestrator._spawn_docker(session)

    assert runtime.ref.startswith("docker://")
    # Expect: initial rm, first run (conflict), rm retry, second run.
    assert runner.calls[0][:3] == ["docker", "rm", "-f"]
    assert runner.calls[1][:3] == ["docker", "run", "-d"]
    assert runner.calls[2][:3] == ["docker", "rm", "-f"]
    assert runner.calls[3][:3] == ["docker", "run", "-d"]


def test_spawn_docker_raises_after_conflict_retry_fails():
    class _RunnerAlwaysConflict(_RunnerConflictThenSuccess):
        def run(self, command, *, cwd=None, env=None, stream=None, allow_failure=False):
            rendered = list(command)
            self.calls.append(rendered)
            if rendered[:3] == ["docker", "run", "-d"]:
                raise subprocess.CalledProcessError(
                    125, rendered, output="Conflict. The container name is already in use."
                )
            return CommandResult(exit_code=0, stdout="", stderr="")

    user = get_user_model().objects.create_user(username="runner2", password="pass12345")
    session = _create_session(user)
    runner = _RunnerAlwaysConflict()
    orchestrator = SandboxOrchestrator(runner=runner)

    with pytest.raises(SandboxProvisionError):
        orchestrator._spawn_docker(session)

    # Should have attempted rm, run, rm, run.
    assert runner.calls[0][:3] == ["docker", "rm", "-f"]
    assert runner.calls[1][:3] == ["docker", "run", "-d"]
    assert runner.calls[2][:3] == ["docker", "rm", "-f"]
    assert runner.calls[3][:3] == ["docker", "run", "-d"]
