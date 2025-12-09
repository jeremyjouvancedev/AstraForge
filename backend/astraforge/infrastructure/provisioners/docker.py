"""Local Docker provisioner used for running Codex CLI in development."""

from __future__ import annotations

from dataclasses import dataclass
import re
import secrets

from astraforge.domain.providers.interfaces import Provisioner


@dataclass
class DockerProvisioner(Provisioner):
    name: str = "docker"
    image: str = "astraforge/codex-cli:latest"

    def spawn(self, repo: str, toolchain: str) -> str:  # pragma: no cover - stub
        suffix = secrets.token_hex(3)
        raw_name = f"codex-{repo}-{toolchain}-{suffix}"
        container_name = self._sanitize(raw_name)
        return f"docker://{container_name}"

    def cleanup(self, ref: str) -> None:  # pragma: no cover - stub
        return None

    def _sanitize(self, value: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-")
        if not sanitized:
            sanitized = "codex-workspace"
        return sanitized.lower()


def from_env() -> DockerProvisioner:
    return DockerProvisioner()
