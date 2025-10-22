"""Claude Code executor adapter with the AgentExecutor protocol."""

from __future__ import annotations

import os
from dataclasses import dataclass

from astraforge.domain.providers.interfaces import AgentExecutor
from astraforge.infrastructure.executors.base import (
    DelegatingExecutor,
    StaticPlanExecutor,
)


@dataclass
class ClaudeCodeSDK:  # pragma: no cover - stub
    api_key: str

    def plan(self, request):
        raise NotImplementedError

    def apply(self, plan, repository, workspace):
        raise NotImplementedError


def from_env() -> AgentExecutor:
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        return StaticPlanExecutor(name="claude-code-static")
    return DelegatingExecutor(name="claude-code", client=ClaudeCodeSDK(api_key=api_key))
