from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path


def _load_codex_wrapper():
    wrapper_path = (
        Path(__file__).resolve().parents[2]
        / "codex_cli_stub"
        / "bin"
        / "codex"
    )
    loader = importlib.machinery.SourceFileLoader("codex_wrapper", str(wrapper_path))
    spec = importlib.util.spec_from_loader(
        "codex_wrapper",
        loader,
        origin=str(wrapper_path),
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_provider_base_url_includes_provider_path():
    wrapper = _load_codex_wrapper()

    assert (
        wrapper._format_provider_base_url("openai", "http://proxy.local")
        == "http://proxy.local/providers/openai"
    )
    assert (
        wrapper._format_provider_base_url("ollama", "http://proxy.local")
        == "http://proxy.local/providers/ollama/v1"
    )


def test_provider_base_url_preserves_prefix_path():
    wrapper = _load_codex_wrapper()

    assert (
        wrapper._format_provider_base_url("openai", "http://proxy.local/prefix")
        == "http://proxy.local/prefix/providers/openai"
    )
    assert (
        wrapper._format_provider_base_url(
            "ollama", "http://proxy.local/prefix/providers/ollama"
        )
        == "http://proxy.local/prefix/providers/ollama/v1"
    )


def test_ensure_config_writes_ollama_env_key_without_wire_api(tmp_path, monkeypatch):
    wrapper = _load_codex_wrapper()
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("CODEX_WRAPPER_MODEL_PROVIDER_WIRE_API", raising=False)
    monkeypatch.delenv("CODEX_WRAPPER_PROVIDER_ENV_KEY", raising=False)

    wrapper._CONFIG_DIR = tmp_path / ".codex"
    wrapper._CONFIG_PATH = wrapper._CONFIG_DIR / "config.toml"

    wrapper._ensure_config("http://proxy.local", "ollama")

    content = wrapper._CONFIG_PATH.read_text(encoding="utf-8")
    assert 'env_key = "OLLAMA_API_KEY"' in content
    assert "wire_api" not in content
    assert "context_window = 16384" in content


def test_context_window_override_only_for_ollama(tmp_path, monkeypatch):
    wrapper = _load_codex_wrapper()
    monkeypatch.setenv("OLLAMA_CONTEXT_WINDOW", "8192")

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    wrapper._CONFIG_DIR = tmp_path / "openai"
    wrapper._CONFIG_PATH = wrapper._CONFIG_DIR / "config.toml"
    wrapper._ensure_config("http://proxy.local", "openai")
    openai_content = wrapper._CONFIG_PATH.read_text(encoding="utf-8")
    assert "context_window" not in openai_content

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    wrapper._CONFIG_DIR = tmp_path / "ollama"
    wrapper._CONFIG_PATH = wrapper._CONFIG_DIR / "config.toml"
    wrapper._ensure_config("http://proxy.local", "ollama")
    ollama_content = wrapper._CONFIG_PATH.read_text(encoding="utf-8")
    assert "context_window = 8192" in ollama_content
