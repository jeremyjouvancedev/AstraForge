from __future__ import annotations

import json

from astraforge_toolkit.backend import _SandboxBackend


class _DummyRt:
    def __init__(self, session_id: str | None = None):
        self.config = {"configurable": {"sandbox_session_id": session_id} if session_id else {}}


class _DummySession:
    def __init__(self, *, get_json: dict, post_json: dict):
        self.get_calls: list[tuple[str, dict]] = []
        self.post_calls: list[tuple[str, dict]] = []
        self._get_json = get_json
        self._post_json = post_json

    def get(self, url, **kwargs):  # type: ignore[override]
        self.get_calls.append((url, kwargs))
        from requests import Response

        response = Response()
        response.status_code = 200
        response._content = json.dumps(self._get_json).encode("utf-8")
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


def test_http_backend_autorestores_when_session_not_ready():
    get_json = {
        "id": "old-session",
        "status": "terminated",
        "workspace_path": "/workspace-old",
        "metadata": {"latest_snapshot_id": "snap-123"},
    }
    post_json = {"id": "new-session", "workspace_path": "/workspace-new"}
    session = _DummySession(get_json=get_json, post_json=post_json)
    rt = _DummyRt(session_id="old-session")

    backend = _SandboxBackend(
        rt,
        base_url="http://localhost/api",
        api_key="key",
        root_dir="/workspace-old",
        session=session,
    )

    restored_session_id = backend._ensure_session_ready()

    assert restored_session_id == "new-session"
    assert backend._workspace_root == "/workspace-new"
    assert session.get_calls and session.post_calls  # GET existing, POST new with restore
    post_url, post_kwargs = session.post_calls[0]
    assert post_url.endswith("/sandbox/sessions/")
    assert post_kwargs["json"]["restore_snapshot_id"] == "snap-123"
