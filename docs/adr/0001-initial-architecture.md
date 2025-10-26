# ADR 0001: Initial Architecture Baseline

- **Status**: Accepted
- **Context**: AstraForge needs a modular platform orchestrating AI agents, connectors, and VCS providers.
- **Decision**: Adopt a hexagonal architecture with domain-first design, plugin registries for provider types, and an event-driven workflow. Backend uses Django REST Framework + Celery; frontend uses React + shadcn/ui. Shared message contracts stored in `shared/`.
- **Consequences**:
  - Clear separation between core domain and adapters.
  - Swappable providers via dependency injection and environment configuration.
  - Additional build pipelines required for multi-service deployment.
