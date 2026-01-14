from __future__ import annotations

from types import SimpleNamespace

from kubernetes.client import ApiException

from astraforge.infrastructure.provisioners.k8s import KubernetesProvisioner


class _FakeApi:
    def __init__(self):
        self.pods = {}
        self.created = 0

    def create_namespaced_pod(self, namespace, body):
        name = body.metadata.name
        if name in self.pods:
            raise ApiException(status=409, reason="AlreadyExists")
        self.created += 1
        self.pods[name] = body

    def read_namespaced_pod(self, name, namespace):
        pod = self.pods.get(name)
        if not pod:
            raise ApiException(status=404, reason="NotFound")
        pod.status = SimpleNamespace(
            phase="Running",
            container_statuses=[SimpleNamespace(ready=True)],
            reason=None,
            message=None,
        )
        return pod


def test_k8s_pod_name_stable_per_sandbox_session():
    provisioner = KubernetesProvisioner(namespace="default")
    session_id = "123e4567-e89b-12d3-a456-426614174000"

    first = provisioner._build_pod_name(session_id, "sandbox")
    second = provisioner._build_pod_name(session_id, "sandbox")

    assert first == second
    assert session_id in first
    assert first.startswith("sandbox-")


def test_k8s_spawn_reuses_existing_sandbox_pod():
    provisioner = KubernetesProvisioner(namespace="default", poll_interval=0)
    provisioner._api = _FakeApi()
    session_id = "e3b0c442-98fc-1c14-9afb-f4c8996fb924"

    ref_one = provisioner.spawn(repo=session_id, toolchain="sandbox")
    ref_two = provisioner.spawn(repo=session_id, toolchain="sandbox")

    pod_name = provisioner._build_pod_name(session_id, "sandbox")
    assert ref_one == ref_two
    assert f"/{pod_name}" in ref_one
    assert provisioner._api.created == 1
