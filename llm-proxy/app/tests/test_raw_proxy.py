from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from app import main


def test_build_upstream_url_prefixes_base_path() -> None:
    url = main._build_upstream_url("https://api.openai.com/v1", "/responses", "")
    assert url == "https://api.openai.com/v1/responses"


def test_build_upstream_url_avoids_double_prefix() -> None:
    url = main._build_upstream_url("http://ollama.local/v1", "/v1/chat/completions", "")
    assert url == "http://ollama.local/v1/chat/completions"


def test_build_upstream_url_preserves_query() -> None:
    url = main._build_upstream_url(
        "http://ollama.local", "/v1/chat/completions", "foo=bar"
    )
    assert url == "http://ollama.local/v1/chat/completions?foo=bar"
