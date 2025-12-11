"""Kubernetes provisioner implementation."""

from __future__ import annotations

import os
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Tuple

from kubernetes import client, config
from kubernetes.client import ApiException
from kubernetes.config.config_exception import ConfigException

from astraforge.domain.providers.interfaces import Provisioner


class WorkspaceProvisioningError(RuntimeError):
    """Raised when a Kubernetes workspace cannot be created or becomes unhealthy."""


@dataclass
class KubernetesProvisioner(Provisioner):
    namespace: str
    image: str = "astraforge/codex-cli:latest"
    service_account: str | None = None
    startup_timeout: int = 180
    poll_interval: int = 2
    volume_mount_path: str = "/workspaces"
    name: str = "k8s"
    _api: client.CoreV1Api | None = field(default=None, init=False, repr=False)

    def spawn(self, repo: str, toolchain: str) -> str:
        pod_name = self._build_pod_name(repo, toolchain)
        api = self._ensure_api()
        pod = self._build_pod(pod_name)
        try:
            api.create_namespaced_pod(namespace=self.namespace, body=pod)
        except ApiException as exc:  # pragma: no cover - surface rich error upstream
            raise WorkspaceProvisioningError(
                f"Failed to create workspace pod {pod_name}: {exc.reason}"
            ) from exc
        self._wait_until_ready(api, pod_name)
        return f"k8s://{self.namespace}/{pod_name}"

    def cleanup(self, ref: str) -> None:
        namespace, name = self._parse_ref(ref)
        api = self._ensure_api()
        try:
            api.delete_namespaced_pod(
                name=name,
                namespace=namespace,
                grace_period_seconds=0,
                propagation_policy="Background",
            )
        except ApiException as exc:  # pragma: no cover - ignore missing pods
            if exc.status not in (404, 410):
                raise

    # internal helpers -----------------------------------------------------

    def _ensure_api(self) -> client.CoreV1Api:
        if self._api is not None:
            return self._api
        try:
            config.load_incluster_config()
        except ConfigException:
            try:
                config.load_kube_config()
            except ConfigException as exc:  # pragma: no cover - configuration error
                raise WorkspaceProvisioningError(
                    "Unable to load Kubernetes configuration for workspace provisioner"
                ) from exc
        self._api = client.CoreV1Api()
        return self._api

    def _build_pod(self, name: str) -> client.V1Pod:
        metadata = client.V1ObjectMeta(
            name=name,
            namespace=self.namespace,
            labels={
                "app.kubernetes.io/name": "astraforge-workspace",
                "astraforge.dev/workspace": name,
            },
        )
        workspace_volume = client.V1Volume(
            name="workspace", empty_dir=client.V1EmptyDirVolumeSource()
        )
        volume_mount = client.V1VolumeMount(name="workspace", mount_path=self.volume_mount_path)
        container_security = client.V1SecurityContext(
            allow_privilege_escalation=False,
            privileged=False,
            read_only_root_filesystem=True,
            run_as_non_root=True,
            capabilities=client.V1Capabilities(drop=["ALL"]),
            seccomp_profile=client.V1SeccompProfile(type="RuntimeDefault"),
        )
        container = client.V1Container(
            name="codex",
            image=self.image,
            image_pull_policy="IfNotPresent",
            command=["sleep", "infinity"],
            volume_mounts=[volume_mount],
            security_context=container_security,
        )
        pod_security_context = client.V1PodSecurityContext(
            run_as_non_root=True,
            run_as_user=1000,
            run_as_group=1000,
            fs_group=1000,
            seccomp_profile=client.V1SeccompProfile(type="RuntimeDefault"),
        )
        spec = client.V1PodSpec(
            containers=[container],
            restart_policy="Never",
            volumes=[workspace_volume],
            service_account_name=self.service_account,
            security_context=pod_security_context,
            automount_service_account_token=False,
        )
        return client.V1Pod(metadata=metadata, spec=spec)

    def _wait_until_ready(self, api: client.CoreV1Api, name: str) -> None:
        deadline = time.time() + self.startup_timeout
        while time.time() < deadline:
            try:
                pod = api.read_namespaced_pod(name=name, namespace=self.namespace)
            except ApiException as exc:
                if exc.status == 404:
                    time.sleep(self.poll_interval)
                    continue
                raise
            phase = (pod.status.phase or "").lower()
            if phase == "running":
                statuses = pod.status.container_statuses or []
                if all(status.ready for status in statuses):
                    return
            if phase in {"failed", "unknown"}:
                message = pod.status.message or pod.status.reason or "unknown"
                raise WorkspaceProvisioningError(
                    f"Workspace pod {name} failed during startup: {message}"
                )
            time.sleep(self.poll_interval)
        raise WorkspaceProvisioningError(
            f"Timed out waiting for workspace pod {name} to become ready"
        )

    def _build_pod_name(self, repo: str, toolchain: str) -> str:
        base = f"{repo}-{toolchain}".lower()
        slug = re.sub(r"[^a-z0-9-]+", "-", base).strip("-") or "workspace"
        suffix = secrets.token_hex(3)
        trimmed = slug[: max(0, 50)]
        return f"codex-{trimmed}-{suffix}"

    def _parse_ref(self, ref: str) -> Tuple[str, str]:
        identifier = ref
        if "://" in ref:
            _, identifier = ref.split("://", 1)
        if "/" in identifier:
            namespace, name = identifier.split("/", 1)
            return namespace, name
        return self.namespace, identifier


def _detect_namespace() -> str:
    for path in (
        os.getenv("KUBERNETES_NAMESPACE_FILE"),
        "/var/run/secrets/kubernetes.io/serviceaccount/namespace",
    ):
        if not path:
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                content = handle.read().strip()
                if content:
                    return content
        except FileNotFoundError:
            continue
    return os.getenv("KUBERNETES_NAMESPACE") or os.getenv("ASTRAFORGE_K8S_NAMESPACE") or "default"


def from_env() -> KubernetesProvisioner:
    namespace = _detect_namespace()
    image = os.getenv("CODEX_WORKSPACE_IMAGE") or os.getenv("KUBERNETES_WORKSPACE_IMAGE") or os.getenv(
        "ASTRAFORGE_K8S_IMAGE", "astraforge/codex-cli:latest"
    )
    service_account = os.getenv("KUBERNETES_SERVICE_ACCOUNT")
    timeout = int(os.getenv("KUBERNETES_WORKSPACE_TIMEOUT", "180"))
    return KubernetesProvisioner(
        namespace=namespace,
        image=image,
        service_account=service_account,
        startup_timeout=timeout,
    )
