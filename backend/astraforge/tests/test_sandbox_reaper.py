from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from astraforge.domain.models.workspace import CommandResult
from astraforge.sandbox.models import SandboxSession
from astraforge.sandbox.reaper import SandboxReaper
from astraforge.sandbox.services import SandboxOrchestrator

pytestmark = pytest.mark.django_db


class _RunnerSpy:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, command, *, cwd=None, env=None, stream=None, allow_failure=False) -> CommandResult:
        rendered = list(command)
        self.commands.append(rendered)
        return CommandResult(exit_code=0, stdout="", stderr="")


def _create_session(user, **overrides) -> SandboxSession:
    defaults = {
        "mode": SandboxSession.Mode.DOCKER,
        "image": "astraforge/codex-cli:latest",
        "status": SandboxSession.Status.READY,
        "ref": "docker://sandbox-test",
        "control_endpoint": "docker://sandbox-test",
        "workspace_path": "/workspace",
        "idle_timeout_sec": 60,
        "max_lifetime_sec": 3600,
    }
    defaults.update(overrides)
    return SandboxSession.objects.create(user=user, **defaults)


def test_reaper_terminates_idle_sessions():
    user = get_user_model().objects.create_user(username="sandboxer", password="pass12345")
    session = _create_session(user)
    session.last_activity_at = timezone.now() - timedelta(minutes=10)
    session.save(update_fields=["last_activity_at"])

    runner = _RunnerSpy()
    reaper = SandboxReaper(orchestrator=SandboxOrchestrator(runner=runner))

    result = reaper.reap(now=timezone.now())

    session.refresh_from_db()
    assert result == {"checked": 1, "terminated": 1}
    assert session.status == SandboxSession.Status.TERMINATED
    assert session.metadata.get("terminated_reason") == "idle_timeout"
    assert any(cmd[:3] == ["docker", "rm", "-f"] for cmd in runner.commands)


def test_reaper_skips_recent_sessions():
    user = get_user_model().objects.create_user(username="sandboxer2", password="pass12345")
    session = _create_session(user, idle_timeout_sec=300)
    session.last_activity_at = timezone.now() - timedelta(seconds=30)
    session.save(update_fields=["last_activity_at"])

    runner = _RunnerSpy()
    reaper = SandboxReaper(orchestrator=SandboxOrchestrator(runner=runner))

    result = reaper.reap(now=timezone.now())

    session.refresh_from_db()
    assert result == {"checked": 1, "terminated": 0}
    assert session.status == SandboxSession.Status.READY
    assert session.metadata.get("terminated_reason") is None
    assert runner.commands == []


def test_reaper_enforces_max_lifetime():
    user = get_user_model().objects.create_user(username="sandboxer3", password="pass12345")
    past = timezone.now() - timedelta(hours=2)
    session = _create_session(
        user,
        expires_at=past,
        max_lifetime_sec=1800,
        idle_timeout_sec=1800,
    )

    runner = _RunnerSpy()
    reaper = SandboxReaper(orchestrator=SandboxOrchestrator(runner=runner))

    result = reaper.reap(now=timezone.now())

    session.refresh_from_db()
    assert result == {"checked": 1, "terminated": 1}
    assert session.status == SandboxSession.Status.TERMINATED
    assert session.metadata.get("terminated_reason") == "max_lifetime"
