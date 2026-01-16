from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

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


def test_proxy_ollama_responses_non_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.local")

    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def aclose(self) -> None:
            return None

        async def post(self, url: str, *, json: dict[str, object]):
            captured["url"] = url
            captured["json"] = json
            return httpx.Response(
                200,
                json={"message": {"content": "Hello from Ollama"}},
            )

        def stream(self, *args, **kwargs):  # noqa: D401 - test helper
            raise AssertionError("stream should not be invoked for non-stream payloads")

    monkeypatch.setattr(main, "httpx", main.httpx)
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(main._proxy_ollama_responses({"input": "Hello"}))

    assert result["object"] == "response"
    assert result["output"][0]["content"][0]["text"] == "Hello from Ollama"
    assert captured["url"] == "http://ollama.local/api/chat"
    assert captured["json"]["messages"] == [{"role": "user", "content": "Hello"}]


def test_default_model_prefers_ollama_over_llm_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OLLAMA_MODEL", "devstral-small-2:24b")
    main._llm_provider.cache_clear()

    assert main._default_model() == "devstral-small-2:24b"


def test_ollama_stream_iterator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.local")

    class FakeStreamContext:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers = {"content-type": "application/x-ndjson"}
            self._lines = [
                json.dumps({"message": {"content": "Hello"}, "done": False}),
                json.dumps({"message": {"content": " world"}, "done": True}),
            ]

        async def __aenter__(self) -> "FakeStreamContext":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def aread(self) -> bytes:
            return b""

        def aiter_lines(self):
            async def generator():
                for line in self._lines:
                    yield line

            return generator()

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def aclose(self) -> None:
            return None

        def stream(self, method: str, url: str, *, json: dict[str, object]):
            assert method == "POST"
            assert json.get("stream") is True
            return FakeStreamContext()

        async def post(self, *args, **kwargs):
            raise AssertionError("post should not be invoked for streaming payloads")

    monkeypatch.setattr(main, "httpx", main.httpx)
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeAsyncClient)

    async def run() -> list[str]:
        iterator, _status, _headers = await main._ollama_stream_iterator(
            {"input": "Hello", "stream": True}
        )
        output_lines: list[str] = []
        async for chunk in iterator:
            output_lines.extend(chunk.decode().splitlines())
        return output_lines

    lines = asyncio.run(run())
    payloads = [line[6:] for line in lines if line.startswith("data: ")]
    assert any('"response.output_text.delta"' in payload for payload in payloads)
    assert any('"response.completed"' in payload for payload in payloads)
