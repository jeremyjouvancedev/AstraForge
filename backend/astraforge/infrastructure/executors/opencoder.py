"""OpenCoder executor adapter with the AgentExecutor protocol."""

from __future__ import annotations

import os
from dataclasses import dataclass

from astraforge.domain.providers.interfaces import AgentExecutor
from astraforge.infrastructure.executors.base import (
    DelegatingExecutor,
    StaticPlanExecutor,
)


@dataclass
class OpenCoderSDK:  # pragma: no cover - stub
    api_key: str

    def plan(self, request):
        raise NotImplementedError

    def apply(self, plan, repository, workspace):
        raise NotImplementedError


def from_env() -> AgentExecutor:
    api_key = os.getenv("OPENCODER_API_KEY")
    if not api_key:
        return StaticPlanExecutor(name="open-coder-static")
    return DelegatingExecutor(name="open-coder", client=OpenCoderSDK(api_key=api_key))
