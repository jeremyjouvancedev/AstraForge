from astraforge.interfaces.providers.registry import Container, ProviderRegistry


def test_provider_registry_resolve():
    registry: ProviderRegistry[int] = ProviderRegistry()
    registry.register("one", lambda: 1)
    assert registry.resolve("one") == 1


def test_container_resolve_explicit_key():
    container = Container()
    container.executors.register("codex", lambda: "executor")
    assert container.resolve_executor("codex") == "executor"
