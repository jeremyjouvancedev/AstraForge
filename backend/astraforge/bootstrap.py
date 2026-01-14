"""Application bootstrap utilities: dependency container and in-memory repositories."""

from __future__ import annotations

from astraforge.infrastructure.ai import mr_author
from astraforge.infrastructure.connectors import base as connector_base
from astraforge.infrastructure.connectors import email, glitchtip, jira, teams
from astraforge.infrastructure.event_bus import memory as memory_stream, redis_streams
from astraforge.infrastructure.executors import claude, codex, opencoder
from astraforge.infrastructure.provisioners import docker, k8s
from astraforge.infrastructure.repositories import DjangoRequestRepository, InMemoryRequestRepository
from astraforge.infrastructure.vcs import gitlab
from astraforge.infrastructure.workspaces import codex as codex_workspace
from astraforge.infrastructure.vector_store import pgvector
from astraforge.interfaces.providers.registry import Container

container = Container()
container.executors.register("codex", codex.from_env)
container.executors.register("claude_code", claude.from_env)
container.executors.register("open_coder", opencoder.from_env)
container.provisioners.register("k8s", k8s.from_env)
container.provisioners.register("docker", docker.from_env)
container.vcs_providers.register("gitlab", gitlab.from_env)
container.vector_stores.register("pgvector", pgvector.from_env)
container.event_buses.register("redis_streams", redis_streams.from_env)
container.run_logs.register("memory", memory_stream.from_env)
container.run_logs.register("redis", redis_streams.from_env)
container.connectors.register("direct_user", connector_base.from_env)
container.connectors.register("jira", jira.from_env)
container.connectors.register("email", email.from_env)
container.connectors.register("teams", teams.from_env)
container.connectors.register("glitchtip", glitchtip.from_env)
container.merge_request_composers.register("proxy", mr_author.from_env)


container.workspace_operators.register(
    "codex",
    lambda: codex_workspace.from_env(container.resolve_provisioner()),
)


def _resolve_repository() -> InMemoryRequestRepository | DjangoRequestRepository:
    try:  # pragma: no cover - settings access optional during tests
        from django.conf import settings

        backend = getattr(settings, "REQUEST_REPOSITORY", "database")
    except Exception:
        backend = "memory"

    if backend == "memory":
        return InMemoryRequestRepository()
    return DjangoRequestRepository()


repository = _resolve_repository()
