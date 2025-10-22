"""Application bootstrap utilities: dependency container and in-memory repositories."""

from __future__ import annotations

from astraforge.infrastructure.connectors import base as connector_base
from astraforge.infrastructure.connectors import email, glitchtip, jira, teams
from astraforge.infrastructure.event_bus import redis_streams
from astraforge.infrastructure.executors import claude, codex, opencoder
from astraforge.infrastructure.provisioners import k8s
from astraforge.infrastructure.repositories.memory import InMemoryRequestRepository
from astraforge.infrastructure.vcs import gitlab
from astraforge.infrastructure.vector_store import pgvector
from astraforge.interfaces.providers.registry import Container

container = Container()
container.executors.register("codex", codex.from_env)
container.executors.register("claude_code", claude.from_env)
container.executors.register("open_coder", opencoder.from_env)
container.provisioners.register("k8s", k8s.from_env)
container.vcs_providers.register("gitlab", gitlab.from_env)
container.vector_stores.register("pgvector", pgvector.from_env)
container.event_buses.register("redis_streams", redis_streams.from_env)
container.connectors.register("direct_user", connector_base.from_env)
container.connectors.register("jira", jira.from_env)
container.connectors.register("email", email.from_env)
container.connectors.register("teams", teams.from_env)
container.connectors.register("glitchtip", glitchtip.from_env)

repository = InMemoryRequestRepository()
