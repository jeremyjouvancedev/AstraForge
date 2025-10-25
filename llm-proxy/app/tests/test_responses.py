from __future__ import annotations

import asyncio
import httpx
import pytest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app import main


def test_proxy_openai_responses_non_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: D401 - test helper
            pass

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: D401 - test helper
            return None

        async def aclose(self) -> None:
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return httpx.Response(200, json={"id": "resp_test", "object": "response"})

        def stream(self, *args, **kwargs):  # noqa: D401 - test helper
            raise AssertionError("stream should not be invoked for non-stream payloads")

    monkeypatch.setattr(main, "httpx", main.httpx)
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(main._proxy_openai_responses({"input": "Hello"}))

    assert result == {"id": "resp_test", "object": "response"}
    assert captured["json"] == {"input": "Hello"}
    assert "Authorization" in captured["headers"]


def test_proxy_responses_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    class FakeStreamContext:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers = {"content-type": "text/event-stream"}
            self._chunks = [b"data: test\n\n"]

        async def __aenter__(self) -> "FakeStreamContext":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def aread(self) -> bytes:
            return b""

        def aiter_bytes(self):
            async def generator():
                for chunk in self._chunks:
                    yield chunk

            return generator()

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: D401 - test helper
            pass

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def aclose(self) -> None:
            return None

        def stream(self, method: str, url: str, *, headers: dict[str, str], json: dict[str, object]):
            assert method == "POST"
            assert json.get("stream") is True
            return FakeStreamContext()

        async def post(self, *args, **kwargs):  # noqa: D401 - test helper
            raise AssertionError("post should not be invoked for streaming payloads")

    monkeypatch.setattr(main, "httpx", main.httpx)
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeAsyncClient)

    async def run() -> tuple[int, dict[str, str], list[bytes]]:
        iterator, status, headers = await main._openai_stream_iterator(
            main._openai_responses_url(),
            main._build_openai_headers(),
            {"input": "Hello", "stream": True},
            main.httpx.Timeout(None),
        )
        chunks: list[bytes] = []
        async for chunk in iterator:
            chunks.append(chunk)
        return status, headers, chunks

    status, headers, chunks = asyncio.run(run())

    assert status == 200
    assert headers["Content-Type"] == "text/event-stream"
    assert chunks == [b"data: test\n\n"]
