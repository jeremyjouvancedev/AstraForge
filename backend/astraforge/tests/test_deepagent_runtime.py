from __future__ import annotations

from astraforge.infrastructure.ai import deepagent_runtime


def test_get_deep_agent_registers_slide_subagent(monkeypatch):
    captured: dict[str, object] = {}

    class DummyModel:
        def __init__(self, *args, **kwargs) -> None:  # noqa: D401
            """Lightweight stand-in for ChatOpenAI."""
            self.args = args
            self.kwargs = kwargs

    def fake_create_deep_agent(*, model, backend, system_prompt, tools=None, subagents=None):
        captured["model"] = model
        captured["backend"] = backend
        captured["system_prompt"] = system_prompt
        captured["tools"] = tools
        captured["subagents"] = subagents

        class _DummyAgent:
            def invoke(self, *args, **kwargs):
                return {"messages": []}

        return _DummyAgent()

    deepagent_runtime.get_deep_agent.cache_clear()
    monkeypatch.setattr(deepagent_runtime, "ChatOpenAI", DummyModel)
    monkeypatch.setattr(deepagent_runtime, "create_deep_agent", fake_create_deep_agent)

    _ = deepagent_runtime.get_deep_agent()

    subagents = captured.get("subagents")
    assert isinstance(subagents, list) and subagents
    names = [s.get("name") for s in subagents if isinstance(s, dict)]
    assert "slide-deck-builder" in names

