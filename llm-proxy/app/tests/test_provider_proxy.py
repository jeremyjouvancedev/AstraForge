from __future__ import annotations

from pathlib import Path
import sys

from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app import main


def test_provider_proxy_routes_to_openai(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openai.local/v1")
    captured: dict[str, str | None] = {}

    async def fake_proxy(request, upstream_base_url, *, request_path=None):
        captured["upstream_base_url"] = upstream_base_url
        captured["request_path"] = request_path
        return StreamingResponse(iter([b"ok"]), status_code=200)

    monkeypatch.setattr(main, "_proxy_raw_request", fake_proxy)

    client = TestClient(main.app)
    response = client.post("/providers/openai/v1/chat/completions", json={"ok": True})

    assert response.status_code == 200
    assert captured["upstream_base_url"] == "https://openai.local/v1"
    assert captured["request_path"] == "/v1/chat/completions"


def test_provider_proxy_rejects_unknown_provider() -> None:
    client = TestClient(main.app)
    response = client.post("/providers/unknown/v1/chat/completions")

    assert response.status_code == 404
    assert "Unsupported LLM provider" in response.json()["detail"]


def test_provider_proxy_routes_ollama_responses(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_ollama_responses(payload):
        captured["payload"] = payload
        return StreamingResponse(iter([b"ok"]), status_code=200)

    monkeypatch.setattr(main, "_proxy_ollama_responses", fake_ollama_responses)

    client = TestClient(main.app)
    response = client.post("/providers/ollama/v1/responses", json={"input": "Hello"})

    assert response.status_code == 200
    assert captured["payload"] == {"input": "Hello"}
