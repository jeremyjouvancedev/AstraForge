"""Domain provider interfaces that drive AstraForge plugin architecture."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from astraforge.domain.models.request import ChangeSet, ExecutionPlan, Request


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str


class AgentExecutor(Protocol):
    """Orchestrates LLM agents to plan and apply code changes."""

    def plan(self, request: Request) -> ExecutionPlan:  # pragma: no cover - interface
        ...

    def apply(
        self, plan: ExecutionPlan, repository: str, workspace: str
    ) -> ChangeSet:  # pragma: no cover
        ...


class Connector(Protocol):
    """Transforms inbound payloads (Jira, email, etc.) into internal requests."""

    def parse_inbound(self, payload: dict[str, Any]) -> Request:  # pragma: no cover
        ...

    def ack(self, external_id: str) -> None:  # pragma: no cover
        ...


class VCSProvider(Protocol):
    """Interacts with Git hosting providers to open merge requests and comment on them."""

    def open_mr(
        self, repo: str, branch: str, title: str, body: str, artifacts: Iterable[str]
    ) -> str:  # pragma: no cover
        ...

    def comment(self, mr_ref: str, comments: list[str]) -> None:  # pragma: no cover
        ...


class Provisioner(Protocol):
    """Manages ephemeral execution workspaces (e.g., Kubernetes pods)."""

    def spawn(self, repo: str, toolchain: str) -> str:  # pragma: no cover
        ...

    def cleanup(self, ref: str) -> None:  # pragma: no cover
        ...


class ReviewBot(Protocol):
    """Reviews merge requests and produces automated findings."""

    def review(
        self, mr_ref: str, context: dict[str, Any]
    ) -> dict[str, Any]:  # pragma: no cover
        ...


class VectorStore(Protocol):
    """Stores embeddings for retrieval augmented generation."""

    def upsert(
        self, namespace: str, items: Iterable[dict[str, Any]]
    ) -> None:  # pragma: no cover
        ...

    def query(
        self, namespace: str, query: str, top_k: int = 5
    ) -> list[dict[str, Any]]:  # pragma: no cover
        ...
