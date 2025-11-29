from __future__ import annotations

import os
from functools import lru_cache

from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

from astraforge.sandbox.deepagent_backend import SandboxBackend


@lru_cache(maxsize=1)
def get_deep_agent():
    """Instantiate a singleton deep agent bound to the sandbox backend."""

    def backend_factory(rt):
        return SandboxBackend(rt)

    model_name = os.getenv("DEEPAGENT_MODEL", "gpt-4o")
    temperature = float(os.getenv("DEEPAGENT_TEMPERATURE", "0.3"))
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL") or None
    model = ChatOpenAI(model=model_name, temperature=temperature, api_key=api_key, base_url=base_url)
    system_prompt = os.getenv(
        "DEEPAGENT_SYSTEM_PROMPT",
        (
            "You are a deep coding agent operating inside an isolated sandbox. "
            "Use filesystem tools (ls, read_file, write_file, edit_file, glob, grep) "
            "to explore and modify files in /workspace as needed."
        ),
    )
    return create_deep_agent(model=model, backend=backend_factory, system_prompt=system_prompt)

