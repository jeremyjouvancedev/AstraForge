from __future__ import annotations

import subprocess
import uuid

import pytest
from django.contrib.auth import get_user_model

from astraforge.domain.models.workspace import CommandResult
from astraforge.sandbox.models import SandboxSession, SandboxSnapshot
from astraforge.sandbox.services import SandboxOrchestrator, SandboxProvisionError

pytestmark = pytest.mark.django_db


class _RunnerConflictThenSuccess:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.failed_once = False

    def run(self, command, *, cwd=None, env=None, stream=None, allow_failure=False):
        rendered = list(command)
        self.calls.append(rendered)
        if rendered[:2] == ["docker", "inspect"]:
            return CommandResult(exit_code=1, stdout="", stderr="not found")
        if rendered[:2] == ["docker", "rm"]:
            return CommandResult(exit_code=0, stdout="", stderr="")
        if rendered[:3] == ["docker", "run", "-d"] and not self.failed_once:
            self.failed_once = True
            raise subprocess.CalledProcessError(
                125,
                rendered,
                output="docker: Error response from daemon: Conflict. The container name is already in use.",
            )
        return CommandResult(exit_code=0, stdout="", stderr="")


class _RunnerRecorder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, command, *, cwd=None, env=None, stream=None, allow_failure=False):
        rendered = list(command)
        self.calls.append(rendered)
        if rendered[:2] == ["docker", "inspect"]:
            return CommandResult(exit_code=1, stdout="", stderr="not found")
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
    # Expect: initial inspect, first run (conflict), inspect retry, rm retry, second run.
    assert runner.calls[0][:2] == ["docker", "inspect"]
    assert runner.calls[1][:3] == ["docker", "run", "-d"]
    assert runner.calls[2][:2] == ["docker", "inspect"]
    assert runner.calls[3][:3] == ["docker", "rm", "-f"]
    assert runner.calls[4][:3] == ["docker", "run", "-d"]


def test_spawn_docker_retries_when_marked_for_removal():
    class _RunnerMarkedForRemoval(_RunnerConflictThenSuccess):
        def run(self, command, *, cwd=None, env=None, stream=None, allow_failure=False):
            rendered = list(command)
            self.calls.append(rendered)
            if rendered[:2] == ["docker", "inspect"]:
                return CommandResult(exit_code=1, stdout="", stderr="not found")
            if rendered[:2] == ["docker", "rm"]:
                return CommandResult(exit_code=0, stdout="", stderr="")
            if rendered[:3] == ["docker", "run", "-d"] and not self.failed_once:
                self.failed_once = True
                raise subprocess.CalledProcessError(
                    125,
                    rendered,
                    output="docker: Error response from daemon: Conflict. The container name is already in use by container which is marked for removal and cannot be started.",
                )
            return CommandResult(exit_code=0, stdout="", stderr="")

    user = get_user_model().objects.create_user(username="runner-removal", password="pass12345")
    session = _create_session(user)
    runner = _RunnerMarkedForRemoval()
    orchestrator = SandboxOrchestrator(runner=runner)

    runtime = orchestrator._spawn_docker(session)

    assert runtime.ref.startswith("docker://")
    assert runner.calls[0][:2] == ["docker", "inspect"]
    assert runner.calls[1][:3] == ["docker", "run", "-d"]
    assert runner.calls[2][:2] == ["docker", "inspect"]
    assert runner.calls[3][:3] == ["docker", "rm", "-f"]
    assert runner.calls[4][:3] == ["docker", "run", "-d"]


def test_spawn_docker_raises_after_conflict_retry_fails():
    class _RunnerAlwaysConflict(_RunnerConflictThenSuccess):
        def run(self, command, *, cwd=None, env=None, stream=None, allow_failure=False):
            rendered = list(command)
            self.calls.append(rendered)
            if rendered[:3] == ["docker", "run", "-d"]:
                raise subprocess.CalledProcessError(
                    125, rendered, output="Conflict. The container name is already in use."
                )
            if rendered[:2] == ["docker", "inspect"]:
                return CommandResult(exit_code=1, stdout="", stderr="")
            return CommandResult(exit_code=0, stdout="", stderr="")

    user = get_user_model().objects.create_user(username="runner2", password="pass12345")
    session = _create_session(user)
    runner = _RunnerAlwaysConflict()
    orchestrator = SandboxOrchestrator(runner=runner)

    with pytest.raises(SandboxProvisionError):
        orchestrator._spawn_docker(session)

    # Should have attempted inspect, run, inspect, rm, run, inspect adoption.
    assert runner.calls[0][:2] == ["docker", "inspect"]
    assert runner.calls[1][:3] == ["docker", "run", "-d"]
    assert runner.calls[2][:2] == ["docker", "inspect"]
    assert runner.calls[3][:3] == ["docker", "rm", "-f"]
    assert runner.calls[4][:3] == ["docker", "run", "-d"]
    assert runner.calls[5][:2] == ["docker", "inspect"]


def test_spawn_docker_adopts_conflicting_container():
    class _RunnerConflictThenAdopt:
        def __init__(self, session_id: str) -> None:
            self.calls: list[list[str]] = []
            self.session_id = session_id
            self.seen_conflict = False

        def run(self, command, *, cwd=None, env=None, stream=None, allow_failure=False):
            rendered = list(command)
            self.calls.append(rendered)
            if rendered[:3] == ["docker", "run", "-d"]:
                self.seen_conflict = True
                raise subprocess.CalledProcessError(
                    125, rendered, output="Conflict. The container name is already in use."
                )
            if rendered[:2] == ["docker", "inspect"]:
                if not self.seen_conflict:
                    return CommandResult(exit_code=1, stdout="", stderr="")
                return CommandResult(exit_code=0, stdout=f"{self.session_id} false\n", stderr="")
            if rendered[:2] == ["docker", "start"]:
                return CommandResult(exit_code=0, stdout="", stderr="")
            return CommandResult(exit_code=0, stdout="", stderr="")

    user = get_user_model().objects.create_user(username="runner3", password="pass12345")
    session = _create_session(user)
    runner = _RunnerConflictThenAdopt(str(session.id))
    orchestrator = SandboxOrchestrator(runner=runner)

    runtime = orchestrator._spawn_docker(session)

    assert runtime.ref.startswith("docker://sandbox-")
    assert runner.calls[0][:2] == ["docker", "inspect"]
    assert runner.calls[1][:3] == ["docker", "run", "-d"]
    assert runner.calls[2][:2] == ["docker", "inspect"]
    assert runner.calls[3][:2] == ["docker", "start"]
    assert not any(call[:3] == ["docker", "rm", "-f"] for call in runner.calls)


def test_spawn_docker_reuses_existing_container_before_run():
    class _RunnerAdoptOnly:
        def __init__(self, session_id: str) -> None:
            self.calls: list[list[str]] = []
            self.session_id = session_id

        def run(self, command, *, cwd=None, env=None, stream=None, allow_failure=False):
            rendered = list(command)
            self.calls.append(rendered)
            if rendered[:2] == ["docker", "inspect"]:
                return CommandResult(exit_code=0, stdout=f"{self.session_id} true\n", stderr="")
            return CommandResult(exit_code=0, stdout="", stderr="")

    user = get_user_model().objects.create_user(username="adopter", password="pass12345")
    session = _create_session(user)
    runner = _RunnerAdoptOnly(str(session.id))
    orchestrator = SandboxOrchestrator(runner=runner)

    runtime = orchestrator._spawn_docker(session)

    assert runtime.ref.startswith("docker://sandbox-")
    assert runner.calls[0][:2] == ["docker", "inspect"]
    assert not any(call[:3] == ["docker", "run", "-d"] for call in runner.calls)
    assert not any(call[:3] == ["docker", "rm", "-f"] for call in runner.calls)


def test_spawn_docker_names_container_with_session_id():
    user = get_user_model().objects.create_user(username="namedsession", password="pass12345")
    session = _create_session(user)
    runner = _RunnerRecorder()
    orchestrator = SandboxOrchestrator(runner=runner)

    runtime = orchestrator._spawn_docker(session)

    assert runtime.ref == f"docker://sandbox-{session.id}"
    run_calls = [call for call in runner.calls if call[:3] == ["docker", "run", "-d"]]
    assert len(run_calls) == 1
    args = run_calls[0]
    assert "--name" in args
    assert args[args.index("--name") + 1] == f"sandbox-{session.id}"

def test_restore_snapshot_uses_safe_tar(monkeypatch):
    user = get_user_model().objects.create_user(username="restorer", password="pass12345")
    session = _create_session(user)
    snapshot = SandboxSnapshot.objects.create(
        id=uuid.uuid4(),
        session=session,
        archive_path="/tmp/test-snapshot.tar.gz",
        size_bytes=10,
        label="",
        include_paths=[session.workspace_path],
        exclude_paths=[],
    )

    recorded = {}

    def _fake_execute(self, sess, command, cwd=None):
        recorded["command"] = command
        recorded["cwd"] = cwd
        return CommandResult(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(SandboxOrchestrator, "execute", _fake_execute)
    orchestrator = SandboxOrchestrator()

    orchestrator.restore_snapshot(session, snapshot)

    assert "--no-same-owner" in recorded["command"]
    assert "--no-same-permissions" in recorded["command"]
    assert "--no-overwrite-dir" in recorded["command"]
    assert "-m" in recorded["command"]
    assert "--strip-components=1" in recorded["command"]


def test_spawn_docker_applies_network_and_security(monkeypatch):
    user = get_user_model().objects.create_user(username="secure", password="pass12345")
    session = _create_session(user)
    runner = _RunnerRecorder()
    monkeypatch.setenv("SANDBOX_DOCKER_NETWORK", "astraforge-sandbox")
    monkeypatch.delenv("SANDBOX_DOCKER_USER", raising=False)
    monkeypatch.setenv("SANDBOX_DOCKER_HOST_GATEWAY", "0")
    monkeypatch.setenv("SANDBOX_DOCKER_SECCOMP", "default")
    monkeypatch.setenv("SANDBOX_DOCKER_PIDS_LIMIT", "256")
    monkeypatch.setenv("SANDBOX_DOCKER_READ_ONLY", "1")

    orchestrator = SandboxOrchestrator(runner=runner)
    runtime = orchestrator._spawn_docker(session)

    assert runtime.workspace_path == "/workspace"
    run_calls = [call for call in runner.calls if call[:3] == ["docker", "run", "-d"]]
    assert len(run_calls) == 1
    args = run_calls[0]
    assert "--network" in args and "astraforge-sandbox" in args
    assert "--read-only" in args
    assert "--cap-drop" in args and "ALL" in args
    assert "--security-opt" in args and "no-new-privileges:true" in args
    assert "--pids-limit" in args and "256" in args
    assert any(
        part.startswith("type=tmpfs,target=/workspace,tmpfs-mode=1777") for part in args
    )
    labels = [args[i + 1] for i, arg in enumerate(args) if arg == "--label" and i + 1 < len(args)]
    assert any(label.startswith("astraforge.sandbox.session=") for label in labels)


def test_spawn_docker_honors_custom_user(monkeypatch):
    user = get_user_model().objects.create_user(username="rooty", password="pass12345")
    session = _create_session(user)
    runner = _RunnerRecorder()
    monkeypatch.setenv("SANDBOX_DOCKER_USER", "root")
    orchestrator = SandboxOrchestrator(runner=runner)

    orchestrator._spawn_docker(session)

    run_calls = [call for call in runner.calls if call[:3] == ["docker", "run", "-d"]]
    assert len(run_calls) == 1
    args = run_calls[0]
    assert "--user" in args
    assert args[args.index("--user") + 1] == "root"


def test_spawn_docker_accepts_non_json_inspect_state():
    class _RunnerNonJsonInspect:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def run(self, command, *, cwd=None, env=None, stream=None, allow_failure=False):
            rendered = list(command)
            self.calls.append(rendered)
            if rendered[:2] == ["docker", "inspect"]:
                # First inspect (adoption) should fail, later state inspect returns a non-JSON payload.
                if "-f" in rendered and "{{json .State}}" in rendered:
                    return CommandResult(exit_code=0, stdout="running-ish", stderr="")
                return CommandResult(exit_code=1, stdout="", stderr="not found")
            return CommandResult(exit_code=0, stdout="", stderr="")

    user = get_user_model().objects.create_user(username="statey", password="pass12345")
    session = _create_session(user)
    runner = _RunnerNonJsonInspect()
    orchestrator = SandboxOrchestrator(runner=runner)

    runtime = orchestrator._spawn_docker(session)

    assert runtime.ref.startswith("docker://sandbox-")
    assert not any(call[:2] == ["docker", "start"] for call in runner.calls)
