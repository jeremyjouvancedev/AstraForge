from astraforge.bootstrap import container


def test_container_resolves_singleton_run_log():
    first = container.resolve_run_log()
    second = container.resolve_run_log()
    assert first is second
