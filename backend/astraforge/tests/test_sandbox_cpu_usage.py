import pytest

from astraforge.sandbox.services import SandboxOrchestrator


@pytest.mark.parametrize(
    "payload,expected",
    [
        (
            "__PATH:/sys/fs/cgroup/cpu.stat__\nusage_usec 1250000\nuser_usec 1000000\nsystem_usec 250000\n",
            1.25,
        ),
        (
            "__PATH:/sys/fs/cgroup/cpuacct/cpuacct.usage__\n2000000000\n",
            2.0,
        ),
    ],
)
def test_parse_cpu_usage_payload(payload, expected):
    seconds = SandboxOrchestrator._parse_cpu_usage_payload(payload)
    assert seconds == pytest.approx(expected)


def test_parse_cpu_usage_payload_invalid():
    assert SandboxOrchestrator._parse_cpu_usage_payload("") is None
    assert SandboxOrchestrator._parse_cpu_usage_payload("not-a-number") is None
