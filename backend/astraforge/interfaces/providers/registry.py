"""Simple dependency injection container with provider registry support."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Dict, Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass
class ProviderRegistry(Generic[T]):
    """Maps provider keys (e.g., executor names) to lazily constructed instances."""

    factory_map: Dict[str, Callable[[], T]] = field(default_factory=dict)
    _cache: Dict[str, T] = field(default_factory=dict, init=False, repr=False)

    def register(self, key: str, factory: Callable[[], T]) -> None:
        if key in self.factory_map:
            raise ValueError(f"Provider '{key}' already registered")
        self.factory_map[key] = factory
        if key in self._cache:
            del self._cache[key]

    def resolve(self, key: str) -> T:
        if key in self._cache:
            return self._cache[key]
        try:
            factory = self.factory_map[key]
        except KeyError as exc:  # pragma: no cover - defensive
            raise KeyError(f"Provider '{key}' not found") from exc
        instance = factory()
        self._cache[key] = instance
        return instance


@dataclass
class Container:
    """Minimal DI container orchestrating provider registries."""

    executors: ProviderRegistry[Any] = field(default_factory=ProviderRegistry)
    connectors: ProviderRegistry[Any] = field(default_factory=ProviderRegistry)
    vcs_providers: ProviderRegistry[Any] = field(default_factory=ProviderRegistry)
    provisioners: ProviderRegistry[Any] = field(default_factory=ProviderRegistry)
    review_bots: ProviderRegistry[Any] = field(default_factory=ProviderRegistry)
    vector_stores: ProviderRegistry[Any] = field(default_factory=ProviderRegistry)
    event_buses: ProviderRegistry[Any] = field(default_factory=ProviderRegistry)
    spec_generators: ProviderRegistry[Any] = field(default_factory=ProviderRegistry)
    workspace_operators: ProviderRegistry[Any] = field(default_factory=ProviderRegistry)
    merge_request_composers: ProviderRegistry[Any] = field(default_factory=ProviderRegistry)
    run_logs: ProviderRegistry[Any] = field(default_factory=ProviderRegistry)

    def configure_from_settings(self, settings: Any) -> "Container":
        """Bind default providers using a Django settings-like object."""
        executor_key = getattr(settings, "EXECUTOR_PROVIDER", "codex")
        self.executors.register(
            executor_key,
            lambda: settings.EXECUTOR_FACTORY(executor_key),
        )
        return self

    def resolve_executor(self, key: Optional[str] = None) -> Any:
        target = key or self._default("EXECUTOR_PROVIDER", "codex")
        return self.executors.resolve(target)

    def resolve_connector(self, key: Optional[str] = None) -> Any:
        target = key or self._default("CONNECTOR_PROVIDER", "direct_user")
        return self.connectors.resolve(target)

    def resolve_provisioner(self, key: Optional[str] = None) -> Any:
        target = key or self._default("PROVISIONER", "docker")
        return self.provisioners.resolve(target)

    def resolve_spec_generator(self, key: Optional[str] = None) -> Any:
        target = key or self._default("SPEC_GENERATOR", "proxy")
        return self.spec_generators.resolve(target)

    def resolve_workspace_operator(self, key: Optional[str] = None) -> Any:
        target = key or self._default("WORKSPACE_OPERATOR", "codex")
        return self.workspace_operators.resolve(target)

    def resolve_merge_request_composer(self, key: Optional[str] = None) -> Any:
        target = key or self._default("MR_COMPOSER", "proxy")
        return self.merge_request_composers.resolve(target)

    def resolve_run_log(self, key: Optional[str] = None) -> Any:
        target = key or self._default("RUN_LOG_STREAMER", "memory")
        return self.run_logs.resolve(target)

    def _default(self, attr: str, fallback: str) -> str:
        try:
            from django.conf import settings
            from django.core.exceptions import ImproperlyConfigured
        except Exception:  # pragma: no cover - settings not ready
            return fallback
        try:
            return getattr(settings, attr, fallback)
        except ImproperlyConfigured:
            return fallback
