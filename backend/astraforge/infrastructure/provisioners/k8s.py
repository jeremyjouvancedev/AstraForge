"""Kubernetes provisioner implementation."""

from __future__ import annotations

from dataclasses import dataclass

from astraforge.domain.providers.interfaces import Provisioner


@dataclass
class KubernetesProvisioner(Provisioner):
    namespace_prefix: str
    name: str = "k8s"

    def spawn(self, repo: str, toolchain: str) -> str:  # pragma: no cover
        return f"{self.namespace_prefix}-{repo}-{toolchain}"

    def cleanup(self, ref: str) -> None:  # pragma: no cover
        return None


def from_env() -> KubernetesProvisioner:
    prefix = "astraforge"
    return KubernetesProvisioner(namespace_prefix=prefix)
