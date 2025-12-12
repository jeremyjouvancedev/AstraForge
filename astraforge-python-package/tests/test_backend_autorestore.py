from __future__ import annotations

import json

import pytest

from astraforge_toolkit.backend import _SandboxBackend


class _DummyRt:
    def __init__(self, session_id: str | None = None):
        self.config = {"configurable": {"sandbox_session_id": session_id} if session_id else {}}


class _DummySession:
    def __init__(self, *, get_payloads: list[dict], post_json: dict):
        self.get_calls: list[tuple[str, dict]] = []
        self.post_calls: list[tuple[str, dict]] = []
        self._get_payloads = list(get_payloads)
        self._post_json = post_json

    def get(self, url, **kwargs):  # type: ignore[override]
        self.get_calls.append((url, kwargs))
        from requests import Response

        payload = self._get_payloads.pop(0) if self._get_payloads else {}
        response = Response()
        response.status_code = 200
        response._content = json.dumps(payload).encode("utf-8")
        response.url = url
        return response

    def post(self, url, **kwargs):  # type: ignore[override]
        self.post_calls.append((url, kwargs))
        from requests import Response

        response = Response()
        # Session creation expects 201; shell/uploads expect 200. Here we only exercise creation.
        response.status_code = 201
        response._content = json.dumps(self._post_json).encode("utf-8")
        response.url = url
        return response


class _DummySessionWith404:
    def __init__(self, *, get_payloads: list[dict], post_responses: list[tuple[int, dict]]):
        self.get_calls: list[tuple[str, dict]] = []
        self.post_calls: list[tuple[str, dict]] = []
        self._get_payloads = list(get_payloads)
        self._post_responses = list(post_responses)

    def get(self, url, **kwargs):  # type: ignore[override]
        self.get_calls.append((url, kwargs))
        from requests import Response

        payload = self._get_payloads.pop(0) if self._get_payloads else {}
        response = Response()
        response.status_code = 200
        response._content = json.dumps(payload).encode("utf-8")
        response.url = url
        return response

    def post(self, url, **kwargs):  # type: ignore[override]
        self.post_calls.append((url, kwargs))
        from requests import Response

        status_code, payload = self._post_responses.pop(0)
        response = Response()
        response.status_code = status_code
        response._content = json.dumps(payload).encode("utf-8")
        response.url = url
        return response


def test_http_backend_autorestores_when_session_not_ready():
    get_json = [
        {
            "id": "old-session",
            "status": "terminated",
            "workspace_path": "/workspace-old",
            "metadata": {"latest_snapshot_id": "snap-123"},
        }
    ]
    post_json = {"id": "new-session", "workspace_path": "/workspace-new"}
    session = _DummySession(get_payloads=get_json, post_json=post_json)
    rt = _DummyRt(session_id="old-session")

    backend = _SandboxBackend(
        rt,
        base_url="http://localhost/api",
        api_key="key",
        root_dir="/workspace-old",
        session=session,  # type: ignore[arg-type]
    )

    restored_session_id = backend._ensure_session_ready()

    assert restored_session_id == "new-session"
    assert backend._workspace_root == "/workspace-new"
    assert session.get_calls and session.post_calls  # GET existing, POST new with restore
    post_url, post_kwargs = session.post_calls[0]
    assert post_url.endswith("/sandbox/sessions/")
    assert post_kwargs["json"]["restore_snapshot_id"] == "snap-123"


def test_http_backend_waits_for_starting_session(monkeypatch):
    get_payloads = [
        {
            "id": "old-session",
            "status": "starting",
            "workspace_path": "/workspace-old",
            "metadata": {"latest_snapshot_id": "snap-123"},
        },
        {
            "id": "old-session",
            "status": "ready",
            "workspace_path": "/workspace-ready",
            "metadata": {"latest_snapshot_id": "snap-123"},
        },
    ]
    post_json = {"id": "new-session", "workspace_path": "/workspace-new"}
    session = _DummySession(get_payloads=get_payloads, post_json=post_json)
    rt = _DummyRt(session_id="old-session")
    monkeypatch.setenv("ASTRA_FORGE_SANDBOX_READY_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("ASTRA_FORGE_SANDBOX_READY_TIMEOUT", "1")

    backend = _SandboxBackend(
        rt,
        base_url="http://localhost/api",
        api_key="key",
        root_dir="/workspace-old",
        session=session,  # type: ignore[arg-type]
    )

    ready_session_id = backend._ensure_session_ready()

    assert ready_session_id == "old-session"
    assert backend._workspace_root == "/workspace-ready"
    assert len(session.get_calls) >= 2  # polled until ready
    assert session.post_calls == []  # did not create a fresh session


def test_http_backend_retries_session_creation_after_404(monkeypatch):
    get_json = [
        {
            "id": "pinned-session",
            "status": "terminated",
            "workspace_path": "/workspace-old",
            "metadata": {"latest_snapshot_id": "snap-123"},
        }
    ]
    post_responses = [
        (404, {"detail": "Failed to provision Docker sandbox: container is marked for removal"}),
        (201, {"id": "new-session", "workspace_path": "/workspace-new"}),
    ]
    session = _DummySessionWith404(get_payloads=get_json, post_responses=post_responses)
    rt = _DummyRt(session_id="pinned-session")

    backend = _SandboxBackend(
        rt,
        base_url="http://localhost/api",
        api_key="key",
        root_dir="/workspace-old",
        session=session,  # type: ignore[arg-type]
    )

    restored_session_id = backend._ensure_session_ready()

    assert restored_session_id == "new-session"
    assert backend._workspace_root == "/workspace-new"
    assert len(session.post_calls) == 2
    first_payload = session.post_calls[0][1]["json"]
    second_payload = session.post_calls[1][1]["json"]
    assert first_payload.get("id") == "pinned-session"
    assert "id" not in second_payload  # retries without pinned id after 404


def test_http_backend_drops_snapshot_when_restore_is_corrupted(monkeypatch):
    get_json = [
        {
            "id": "pinned-session",
            "status": "terminated",
            "workspace_path": "/workspace-old",
            "metadata": {"latest_snapshot_id": "snap-123"},
        }
    ]
    post_responses = [
        (404, {"detail": "tar: gzip: stdin: invalid compressed data"}),
        (404, {"detail": "tar: gzip: stdin: invalid compressed data"}),
        (201, {"id": "fresh-session", "workspace_path": "/workspace-fresh"}),
    ]
    session = _DummySessionWith404(get_payloads=get_json, post_responses=post_responses)
    rt = _DummyRt(session_id="pinned-session")

    backend = _SandboxBackend(
        rt,
        base_url="http://localhost/api",
        api_key="key",
        root_dir="/workspace-old",
        session=session,  # type: ignore[arg-type]
    )

    restored_session_id = backend._ensure_session_ready()

    assert restored_session_id == "fresh-session"
    assert backend._workspace_root == "/workspace-fresh"
    assert len(session.post_calls) == 3
    first_payload = session.post_calls[0][1]["json"]
    second_payload = session.post_calls[1][1]["json"]
    third_payload = session.post_calls[2][1]["json"]
    assert first_payload.get("id") == "pinned-session"
    assert "id" not in second_payload and second_payload.get("restore_snapshot_id") == "snap-123"
    assert "restore_snapshot_id" not in third_payload and "id" not in third_payload
