from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model

from astraforge.sandbox.models import SandboxSession, SandboxSnapshot
from astraforge.sandbox.views import SandboxSessionViewSet
from astraforge.sandbox import deepagent_backend

pytestmark = pytest.mark.django_db


class _OrchestratorStub:
    def __init__(self) -> None:
        self.provision_called = False
        self.restore_called_with: SandboxSnapshot | None = None

    def provision(self, session: SandboxSession):
        self.provision_called = True
        session.status = SandboxSession.Status.READY
        session.ref = "docker://auto-restore"
        session.control_endpoint = session.ref
        session.workspace_path = "/workspace"
        session.save(
            update_fields=["status", "ref", "control_endpoint", "workspace_path", "updated_at"]
        )

    def restore_snapshot(self, session: SandboxSession, snapshot: SandboxSnapshot):
        self.restore_called_with = snapshot


def _create_session(user, **overrides) -> SandboxSession:
    defaults = {
        "mode": SandboxSession.Mode.DOCKER,
        "image": "astraforge/codex-cli:latest",
        "status": SandboxSession.Status.TERMINATED,
        "ref": "",
        "control_endpoint": "",
        "workspace_path": "/workspace",
        "idle_timeout_sec": 60,
        "max_lifetime_sec": 3600,
        "metadata": {},
    }
    defaults.update(overrides)
    return SandboxSession.objects.create(user=user, **defaults)


def test_ensure_session_ready_reprovisions_and_restores(monkeypatch):
    user = get_user_model().objects.create_user(username="restorer", password="pass12345")
    session = _create_session(user)
    snapshot = SandboxSnapshot.objects.create(
        id=uuid.uuid4(),
        session=session,
        label="latest",
        archive_path="/workspace/.sandbox-snapshots/latest.tar.gz",
        include_paths=[session.workspace_path],
        exclude_paths=[],
    )
    session.metadata = {"latest_snapshot_id": str(snapshot.id)}
    session.save(update_fields=["metadata"])

    orchestrator = _OrchestratorStub()
    viewset = SandboxSessionViewSet()
    viewset.orchestrator = orchestrator

    restored = viewset._ensure_session_ready(session)

    restored.refresh_from_db()
    assert restored.status == SandboxSession.Status.READY
    assert orchestrator.provision_called is True
    assert orchestrator.restore_called_with == snapshot


def test_deepagent_backend_autorestores_non_ready_session(monkeypatch):
    user = get_user_model().objects.create_user(username="restorer2", password="pass12345")
    session = _create_session(user, status=SandboxSession.Status.TERMINATED, ref="")
    snapshot = SandboxSnapshot.objects.create(
        id=uuid.uuid4(),
        session=session,
        label="latest",
        archive_path="/workspace/.sandbox-snapshots/latest.tar.gz",
        include_paths=[session.workspace_path],
        exclude_paths=[],
    )
    session.metadata = {"latest_snapshot_id": str(snapshot.id)}
    session.save(update_fields=["metadata"])

    class _OrchestratorStub:
        def __init__(self):
            self.provision_called = False
            self.restore_called_with = None

        def provision(self, sess: SandboxSession):
            self.provision_called = True
            sess.status = SandboxSession.Status.READY
            sess.workspace_path = "/workspace"
            sess.ref = "docker://restored"
            sess.control_endpoint = sess.ref
            sess.save(
                update_fields=["status", "workspace_path", "ref", "control_endpoint", "updated_at"]
            )

        def restore_snapshot(self, sess: SandboxSession, snap: SandboxSnapshot):
            self.restore_called_with = snap

        def execute(self, *args, **kwargs):
            class _Result:
                exit_code = 0
                stdout = ""
                stderr = ""

            return _Result()

        def upload_bytes(self, *args, **kwargs):
            return self.execute()

    orchestrator = _OrchestratorStub()
    monkeypatch.setattr(deepagent_backend, "SandboxOrchestrator", lambda: orchestrator)

    rt = type("RT", (), {"config": {"configurable": {"sandbox_session_id": str(session.id)}}})()
    backend = deepagent_backend._SandboxBackend(rt)

    backend._session()  # triggers auto-provision + restore
    session.refresh_from_db()

    assert session.status == SandboxSession.Status.READY
    assert orchestrator.provision_called is True
    assert orchestrator.restore_called_with == snapshot
