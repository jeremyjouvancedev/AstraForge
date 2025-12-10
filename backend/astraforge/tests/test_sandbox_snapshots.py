from __future__ import annotations

import pytest
import boto3
from botocore.stub import ANY, Stubber
from django.contrib.auth import get_user_model

from astraforge.domain.models.workspace import CommandResult
from astraforge.sandbox.models import SandboxSession, SandboxSnapshot
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


def test_create_snapshot_records_latest_metadata():
    user = get_user_model().objects.create_user(username="snapper", password="pass12345")
    session = _create_session(user)
    runner = _RunnerSpy()
    orchestrator = SandboxOrchestrator(runner=runner)

    snapshot = orchestrator.create_snapshot(session, label="auto-stop")

    session.refresh_from_db()
    assert session.metadata["latest_snapshot_id"] == str(snapshot.id)
    assert snapshot.archive_path.startswith("/workspace/.sandbox-snapshots/")
    assert any("tar" in " ".join(cmd) for cmd in runner.commands)


def test_restore_snapshot_updates_metadata_and_executes_tar():
    user = get_user_model().objects.create_user(username="restorer", password="pass12345")
    session = _create_session(user)
    snapshot = SandboxSnapshot.objects.create(
        session=session,
        label="latest",
        archive_path="/workspace/.sandbox-snapshots/restore-me.tar.gz",
        include_paths=[session.workspace_path],
        exclude_paths=[],
    )
    runner = _RunnerSpy()
    orchestrator = SandboxOrchestrator(runner=runner)

    orchestrator.restore_snapshot(session, snapshot)

    session.refresh_from_db()
    assert session.metadata["latest_snapshot_id"] == str(snapshot.id)
    joined_commands = " ".join(" ".join(cmd) for cmd in runner.commands)
    assert "tar -xzf /workspace/.sandbox-snapshots/restore-me.tar.gz -C /" in joined_commands


def test_create_snapshot_uploads_to_s3(monkeypatch):
    user = get_user_model().objects.create_user(username="s3user", password="pass12345")
    session = _create_session(user)
    runner = _RunnerSpy()
    bucket = "astraforge-snapshots"
    monkeypatch.setenv("SANDBOX_S3_BUCKET", bucket)
    client = boto3.client(
        "s3",
        endpoint_url="http://minio:9000",
        aws_access_key_id="key",
        aws_secret_access_key="secret",
        region_name="us-east-1",
        use_ssl=False,
    )
    stubber = Stubber(client)
    stubber.add_response(
        "put_object",
        {},
        {
            "Bucket": bucket,
            "Key": ANY,
            "Body": b"payload",
            "ContentType": "application/gzip",
        },
    )
    stubber.activate()

    orchestrator = SandboxOrchestrator(runner=runner)
    orchestrator._s3_client_cached = client
    monkeypatch.setattr(orchestrator, "_read_file_from_sandbox", lambda *_args, **_kwargs: b"payload")

    snapshot = orchestrator.create_snapshot(session, label="s3-upload")

    stubber.assert_no_pending_responses()
    assert snapshot.s3_key == f"snapshots/{session.id}/{snapshot.id}.tar.gz"
    assert session.metadata["latest_snapshot_id"] == str(snapshot.id)


def test_restore_snapshot_downloads_from_s3(monkeypatch):
    user = get_user_model().objects.create_user(username="restore-s3", password="pass12345")
    session = _create_session(user)
    snapshot = SandboxSnapshot.objects.create(
        session=session,
        label="s3",
        s3_key=f"snapshots/{session.id}/s3.tar.gz",
        archive_path="/workspace/.sandbox-snapshots/s3.tar.gz",
        include_paths=[session.workspace_path],
        exclude_paths=[],
    )
    runner = _RunnerSpy()
    orchestrator = SandboxOrchestrator(runner=runner)
    monkeypatch.setenv("SANDBOX_S3_BUCKET", "astraforge-snapshots")
    orchestrator._s3_bucket = "astraforge-snapshots"
    monkeypatch.setattr(orchestrator, "_s3_client", lambda: object())
    uploaded: list[bytes] = []

    def fake_upload_bytes(_session, path, content):
        uploaded.append(content)
        return CommandResult(exit_code=0, stdout="", stderr="")

    monkeypatch.setattr(orchestrator, "upload_bytes", fake_upload_bytes)
    monkeypatch.setattr(orchestrator, "_download_snapshot_from_s3", lambda _snap: b"payload")

    orchestrator.restore_snapshot(session, snapshot)

    assert uploaded and uploaded[0] == b"payload"
    joined_commands = " ".join(" ".join(cmd) for cmd in runner.commands)
    assert "tar -xzf /workspace/.sandbox-snapshots/s3.tar.gz -C /" in joined_commands
