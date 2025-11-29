from __future__ import annotations

import base64
import os
import shlex
import subprocess
import uuid
from dataclasses import dataclass
from typing import Optional, Sequence

from astraforge.infrastructure.provisioners import k8s as k8s_provisioner
from astraforge.infrastructure.workspaces.codex import CommandRunner
from astraforge.sandbox.models import SandboxArtifact, SandboxSession, SandboxSnapshot


class SandboxProvisionError(RuntimeError):
    """Raised when a sandbox cannot be provisioned or controlled."""


def _commands_enabled() -> bool:
    return os.getenv("ASTRAFORGE_EXECUTE_COMMANDS", "0").lower() in {"1", "true", "yes"}


def _render_command(command: str | Sequence[str]) -> str:
    if isinstance(command, (list, tuple)):
        return shlex.join(str(part) for part in command)
    return str(command)


@dataclass
class SandboxRuntime:
    ref: str
    control_endpoint: str
    workspace_path: str


class SandboxOrchestrator:
    def __init__(self, runner: CommandRunner | None = None):
        self.runner = runner or CommandRunner(dry_run=not _commands_enabled())

    def provision(self, session: SandboxSession) -> SandboxSession:
        if session.mode == SandboxSession.Mode.DOCKER:
            runtime = self._spawn_docker(session)
        elif session.mode == SandboxSession.Mode.KUBERNETES:
            runtime = self._spawn_kubernetes(session)
        else:  # pragma: no cover - guarded by serializer
            raise SandboxProvisionError(f"Unsupported sandbox mode {session.mode}")

        session.ref = runtime.ref
        session.control_endpoint = runtime.control_endpoint
        session.workspace_path = runtime.workspace_path
        session.status = SandboxSession.Status.READY
        session.last_activity_at = session.last_activity_at or session.created_at
        session.last_heartbeat_at = session.last_activity_at
        session.save(
            update_fields=[
                "ref",
                "control_endpoint",
                "workspace_path",
                "status",
                "last_activity_at",
                "last_heartbeat_at",
                "updated_at",
            ]
        )
        return session

    def execute(
        self,
        session: SandboxSession,
        command: str | Sequence[str],
        *,
        cwd: str | None = None,
        timeout_sec: int | None = None,
    ):
        if session.status != SandboxSession.Status.READY:
            raise SandboxProvisionError("Sandbox is not ready for execution")
        workdir = cwd or session.workspace_path
        rendered = _render_command(command)
        if timeout_sec:
            try:
                timeout_value = int(timeout_sec)
                # Use plain integer timeout for broad compatibility (BusyBox/GNU).
                rendered = f"timeout {timeout_value} {rendered}"
            except (ValueError, TypeError):
                pass
        wrapped = self._wrap_exec(session, rendered, workdir=workdir)
        result = self.runner.run(wrapped, allow_failure=True)
        session.mark_activity()
        return result

    def upload(self, session: SandboxSession, path: str, content: bytes):
        directory = os.path.dirname(path.rstrip("/")) or "/"
        encoded = base64.b64encode(content).decode("ascii")
        script = (
            f"mkdir -p {shlex.quote(directory)} && "
            f"echo '{encoded}' | base64 -d > {shlex.quote(path)}"
        )
        return self.execute(session, script)

    def upload_bytes(self, session: SandboxSession, path: str, content: bytes):
        return self.upload(session, path, content)

    def capture_screenshot(
        self,
        session: SandboxSession,
        *,
        timeout_sec: int | None = 30,  # kept for API compatibility
    ) -> bytes:
        """Capture a PNG screenshot from the sandbox X server and return raw bytes."""
        if not _commands_enabled():
            raise SandboxProvisionError("Screenshot capture disabled when command execution is off")
        # Reuse the running X server in the sandbox (DISPLAY is set in the image).
        script = """
set -e
DISPLAY=${DISPLAY:-:99}
TMPFILE=${TMPDIR:-/tmp}/sandbox-screenshot.png
if command -v import >/dev/null 2>&1; then
  DISPLAY="$DISPLAY" import -window root "$TMPFILE"
elif command -v xwd >/dev/null 2>&1 && command -v convert >/dev/null 2>&1; then
  DISPLAY="$DISPLAY" xwd -root -silent | convert xwd:- png:"$TMPFILE"
else
  echo "NO_CAPTURE_TOOL" >&2
  exit 3
fi
base64 "$TMPFILE"
"""
        # Keep timeout optional; most captures should be fast.
        result = self.execute(session, script, cwd=session.workspace_path, timeout_sec=timeout_sec)
        if result.exit_code != 0:
            message = (result.stdout or "").strip() or (result.stderr or "").strip()
            if "NO_CAPTURE_TOOL" in message:
                raise SandboxProvisionError(
                    "Screenshot tooling is not available in the sandbox image. "
                    "Install ImageMagick (import) or x11-apps (xwd) in the sandbox "
                    "image (e.g., sandbox/Dockerfile) and set SANDBOX_IMAGE accordingly."
                )
            raise SandboxProvisionError(f"Screenshot command failed: {message}")
        raw_b64 = (result.stdout or "").strip()
        if not raw_b64:
            raise SandboxProvisionError("Screenshot command produced no output")
        try:
            return base64.b64decode(raw_b64.encode("ascii"))
        except Exception as exc:  # noqa: BLE001
            raise SandboxProvisionError("Unable to decode screenshot output") from exc

    def create_snapshot(
        self,
        session: SandboxSession,
        *,
        label: str = "",
        include_paths: list[str] | None = None,
        exclude_paths: list[str] | None = None,
    ) -> SandboxSnapshot:
        include_paths = include_paths or [session.workspace_path]
        exclude_paths = exclude_paths or []
        snapshot_id = uuid.uuid4()
        key = f"snapshots/{session.id}/{snapshot_id}.tar.gz"
        archive_path = f"/tmp/{snapshot_id}.tar.gz"
        include = " ".join(shlex.quote(path) for path in include_paths)
        exclude_clause = " ".join(f"--exclude={shlex.quote(pattern)}" for pattern in exclude_paths)
        command = f"tar -czf {shlex.quote(archive_path)} {exclude_clause} {include}".strip()
        result = self.execute(session, command)
        if result.exit_code != 0:
            raise SandboxProvisionError(f"Snapshot failed: {result.stdout.strip()}")
        size_cmd = f"stat -c %s {shlex.quote(archive_path)}"
        size_result = self.execute(session, size_cmd)
        try:
            size_bytes = int((size_result.stdout or '0').strip() or 0)
        except ValueError:
            size_bytes = 0
        snapshot = SandboxSnapshot.objects.create(
            id=snapshot_id,
            session=session,
            label=label,
            s3_key=key,
            size_bytes=size_bytes,
            include_paths=include_paths,
            exclude_paths=exclude_paths,
            archive_path=archive_path,
        )
        session.mark_activity()
        return snapshot

    def export_file(
        self,
        session: SandboxSession,
        *,
        path: str,
        filename: str,
        content_type: str = "",
    ) -> SandboxArtifact:
        base64_cmd = f"base64 < {shlex.quote(path)}"
        result = self.execute(session, base64_cmd)
        if result.exit_code != 0:
            raise SandboxProvisionError(
                f"Failed to read file {path}: {(result.stdout or '').strip()}"
            )
        raw_b64 = (result.stdout or "").strip()
        content = base64.b64decode(raw_b64.encode("ascii")) if raw_b64 else b""
        size_bytes = len(content)
        storage_path = path
        download_url = self._build_download_url(session, storage_path)
        artifact = SandboxArtifact.objects.create(
            session=session,
            filename=filename,
            content_type=content_type or "application/octet-stream",
            size_bytes=size_bytes,
            storage_path=storage_path,
            download_url=download_url,
        )
        session.mark_activity()
        return artifact

    def list_artifacts(self, session: SandboxSession):
        return session.artifacts.all()

    def list_snapshots(self, session: SandboxSession):
        return session.snapshots.all()

    def terminate(self, session: SandboxSession):
        if session.mode == SandboxSession.Mode.DOCKER:
            ident = self._extract_ref(session.ref)
            self.runner.run(
                [
                    "docker",
                    "rm",
                    "-f",
                    ident,
                ],
                allow_failure=True,
            )
        elif session.mode == SandboxSession.Mode.KUBERNETES:
            provisioner = self._k8s()
            provisioner.cleanup(session.ref)
        session.status = SandboxSession.Status.TERMINATED
        session.save(update_fields=["status", "updated_at"])

    # internal helpers -------------------------------------------------

    def _spawn_docker(self, session: SandboxSession) -> SandboxRuntime:
        ident = f"sandbox-{str(session.id).replace('-', '')[:12]}"
        self.runner.run(["docker", "rm", "-f", ident], allow_failure=True)

        args = [
            "docker",
            "run",
            "-d",
            "--name",
            ident,
            "--hostname",
            ident,
            "--add-host",
            "host.docker.internal:host-gateway",
        ]
        if session.cpu:
            args.extend(["--cpus", session.cpu])
        if session.memory:
            args.extend(["-m", session.memory])
        args.extend([session.image, "sleep", "infinity"])
        try:
            self.runner.run(args, allow_failure=False)
        except subprocess.CalledProcessError as exc:  # pragma: no cover - surfaced upstream
            session.status = SandboxSession.Status.FAILED
            session.error_message = str(exc.output or exc)
            session.save(update_fields=["status", "error_message", "updated_at"])
            summary = session.error_message.strip() or "Docker workspace startup failed"
            raise SandboxProvisionError(
                f"Failed to provision Docker sandbox: {summary}"
            ) from exc
        return SandboxRuntime(
            ref=f"docker://{ident}",
            control_endpoint=f"docker://{ident}",
            workspace_path=session.workspace_path or "/workspace",
        )

    def _spawn_kubernetes(self, session: SandboxSession) -> SandboxRuntime:
        provisioner = self._k8s()
        provisioner.image = session.image or getattr(provisioner, "image", "")
        try:
            ref = provisioner.spawn(repo=str(session.id), toolchain="sandbox")
        except Exception as exc:  # pragma: no cover - configuration errors
            session.status = SandboxSession.Status.FAILED
            session.error_message = str(exc)
            session.save(update_fields=["status", "error_message", "updated_at"])
            raise SandboxProvisionError("Failed to provision Kubernetes sandbox") from exc
        workspace_path = getattr(provisioner, "volume_mount_path", "/workspaces")
        return SandboxRuntime(
            ref=ref,
            control_endpoint=ref,
            workspace_path=workspace_path,
        )

    def _wrap_exec(self, session: SandboxSession, payload: str, *, workdir: Optional[str]):
        mode, identifier = self._split_ref(session.ref)
        script = payload
        if workdir:
            script = f"cd {shlex.quote(workdir)} && {payload}"
        if mode == SandboxSession.Mode.DOCKER:
            base = ["docker", "exec", identifier]
        else:
            namespace, pod = self._split_k8s_identifier(identifier)
            base = ["kubectl", "exec"]
            if namespace:
                base.extend(["-n", namespace])
            base.append(pod)
            base.append("--")
        return base + ["sh", "-c", script]

    def _split_ref(self, ref: str) -> tuple[str, str]:
        if "://" in ref:
            mode, identifier = ref.split("://", 1)
        else:
            mode, identifier = "docker", ref
        return mode, identifier

    def _split_k8s_identifier(self, identifier: str) -> tuple[str | None, str]:
        if "/" in identifier:
            namespace, pod = identifier.split("/", 1)
            return (namespace or None, pod)
        return None, identifier

    def _extract_ref(self, ref: str) -> str:
        return self._split_ref(ref)[1]

    def _k8s(self):
        return k8s_provisioner.from_env()

    def _build_download_url(self, session: SandboxSession, storage_path: str) -> str:
        base = session.artifact_base_url or os.getenv("SANDBOX_ARTIFACT_BASE_URL", "")
        if not base:
            return ""
        return base.rstrip("/") + "/" + storage_path.lstrip("/")
