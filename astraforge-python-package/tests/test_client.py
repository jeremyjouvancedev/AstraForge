import json

from requests import Response, Session

from astraforge_toolkit.client import DeepAgentClient


class DummySession(Session):
    def __init__(self, *, post_json: dict | None = None, get_content: bytes = b""):
        super().__init__()
        self.post_calls: list[tuple[str, dict]] = []
        self.get_calls: list[tuple[str, dict]] = []
        self._post_json = post_json or {}
        self._get_content = get_content

    def post(self, url, **kwargs):  # type: ignore[override]
        self.post_calls.append((url, kwargs))
        response = Response()
        response.status_code = 200
        response._content = json.dumps(self._post_json).encode("utf-8")
        response.url = url
        return response

    def get(self, url, **kwargs):  # type: ignore[override]
        self.get_calls.append((url, kwargs))
        response = Response()
        response.status_code = 200
        response._content = self._get_content
        response.url = url
        return response


def test_upload_file_posts_with_trailing_slash_and_bytes_body():
    session = DummySession(post_json={"ok": True})
    client = DeepAgentClient(base_url="http://localhost/api", api_key="key", session=session)

    result = client.upload_file("abc", "/workspace/test.txt", content="hello")

    assert result == {"ok": True}
    assert len(session.post_calls) == 1
    url, kwargs = session.post_calls[0]
    assert url.endswith("/sandbox/sessions/abc/files/upload/")
    assert kwargs["params"] == {"path": "/workspace/test.txt"}
    assert kwargs["data"] == b"hello"
    assert kwargs["headers"]["Content-Type"] == "application/octet-stream"


def test_get_file_content_uses_trailing_slash_and_decodes_text():
    session = DummySession(get_content=b"hello")
    client = DeepAgentClient(base_url="http://localhost/api", api_key="key", session=session)

    content = client.get_file_content("abc", "/workspace/test.txt", encoding="utf-8")

    assert content == "hello"
    assert len(session.get_calls) == 1
    url, kwargs = session.get_calls[0]
    assert url.endswith("/sandbox/sessions/abc/files/content/")
    assert kwargs["params"] == {"path": "/workspace/test.txt"}


def test_get_file_content_replaces_invalid_bytes_on_decode():
    session = DummySession(get_content=b"\xff\xfehello")
    client = DeepAgentClient(base_url="http://localhost/api", api_key="key", session=session)

    content = client.get_file_content("abc", "/workspace/test.bin", encoding="utf-8")

    assert isinstance(content, str)
    assert "hello" in content
