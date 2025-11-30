from __future__ import annotations

from django.test import override_settings

from astraforge.infrastructure.ai import deepagent_runtime


def test_get_deep_agent_registers_slide_subagent(monkeypatch):
    captured: dict[str, object] = {}

    class DummyModel:
        def __init__(self, *args, **kwargs) -> None:  # noqa: D401
            """Lightweight stand-in for ChatOpenAI."""
            self.args = args
            self.kwargs = kwargs

    def fake_build_checkpointer():
        return object()

    def fake_create_deep_agent(
        *, model, backend, system_prompt, tools=None, subagents=None, checkpointer=None
    ):
        captured["model"] = model
        captured["backend"] = backend
        captured["system_prompt"] = system_prompt
        captured["tools"] = tools
        captured["subagents"] = subagents
        captured["checkpointer"] = checkpointer

        class _DummyAgent:
            def invoke(self, *args, **kwargs):
                return {"messages": []}

        return _DummyAgent()

    deepagent_runtime.get_deep_agent.cache_clear()
    monkeypatch.setattr(deepagent_runtime, "ChatOpenAI", DummyModel)
    monkeypatch.setattr(deepagent_runtime, "_build_checkpointer", fake_build_checkpointer)
    monkeypatch.setattr(deepagent_runtime, "create_deep_agent", fake_create_deep_agent)

    _ = deepagent_runtime.get_deep_agent()

    subagents = captured.get("subagents")
    assert isinstance(subagents, list) and subagents
    names = [s.get("name") for s in subagents if isinstance(s, dict)]
    assert "slide-deck-builder" in names

    # Optional checkpointer is threaded through when available.
    assert captured.get("checkpointer") is not None


def test_checkpointer_dsn_prioritizes_override(monkeypatch):
    monkeypatch.setenv("DEEPAGENT_CHECKPOINTER_URL", "postgres://override")
    monkeypatch.setenv("DATABASE_URL", "postgres://api_db")

    monkeypatch.setattr(
        deepagent_runtime, "_get_database_url_from_django_settings", lambda: "postgres://django"
    )
    assert deepagent_runtime._get_checkpointer_dsn() == "postgres://override"


def test_checkpointer_dsn_falls_back_to_database_url(monkeypatch):
    monkeypatch.delenv("DEEPAGENT_CHECKPOINTER_URL", raising=False)
    monkeypatch.setattr(
        deepagent_runtime, "_get_database_url_from_django_settings", lambda: None
    )
    monkeypatch.setenv("DATABASE_URL", "postgres://api_db")

    assert deepagent_runtime._get_checkpointer_dsn() == "postgres://api_db"


def test_checkpointer_dsn_prefers_django_settings(monkeypatch):
    monkeypatch.delenv("DEEPAGENT_CHECKPOINTER_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        deepagent_runtime, "_get_database_url_from_django_settings", lambda: "postgres://django"
    )

    assert deepagent_runtime._get_checkpointer_dsn() == "postgres://django"


def test_checkpointer_dsn_none_without_config(monkeypatch):
    monkeypatch.delenv("DEEPAGENT_CHECKPOINTER_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        deepagent_runtime, "_get_database_url_from_django_settings", lambda: None
    )

    assert deepagent_runtime._get_checkpointer_dsn() is None


def test_postgres_dsn_from_db_settings_builds_url():
    settings = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "astraforge",
        "USER": "astraforge",
        "PASSWORD": "secret",
        "HOST": "postgres",
        "PORT": "5432",
    }

    assert (
        deepagent_runtime._postgres_dsn_from_db_settings(settings)
        == "postgresql://astraforge:secret@postgres:5432/astraforge"
    )


def test_postgres_dsn_from_db_settings_returns_none_for_non_postgres():
    settings = {"ENGINE": "django.db.backends.sqlite3", "NAME": "db.sqlite3"}

    assert deepagent_runtime._postgres_dsn_from_db_settings(settings) is None


def test_get_database_url_from_django_settings_respects_override():
    db_settings = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "astraforge",
        "USER": "astraforge",
        "PASSWORD": "secret",
        "HOST": "postgres",
        "PORT": "5432",
    }
    with override_settings(DATABASES={"default": db_settings}):
        assert (
            deepagent_runtime._get_database_url_from_django_settings()
            == "postgresql://astraforge:secret@postgres:5432/astraforge"
        )


def test_get_database_url_from_django_settings_returns_none_without_database():
    with override_settings(DATABASES={}):
        assert deepagent_runtime._get_database_url_from_django_settings() is None


def test_checkpointer_dsn_none_without_config(monkeypatch):
    monkeypatch.delenv("DEEPAGENT_CHECKPOINTER_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        deepagent_runtime, "_get_database_url_from_django_settings", lambda: None
    )

    assert deepagent_runtime._get_checkpointer_dsn() is None
