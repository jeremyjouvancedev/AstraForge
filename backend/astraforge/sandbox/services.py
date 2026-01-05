from __future__ import annotations

import base64
import json
import logging
import os
import re
import shlex
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.utils import timezone
from kubernetes.stream import stream as k8s_stream

from astraforge.infrastructure.cpu_usage import (
    CPU_CGROUP_PATHS,
    build_cpu_probe_script,
    parse_cpu_usage_payload,
)
from astraforge.infrastructure.provisioners import k8s as k8s_provisioner
from astraforge.infrastructure.workspaces.codex import CommandRunner
from astraforge.quotas.services import get_quota_service
from astraforge.sandbox.models import SandboxArtifact, SandboxSession, SandboxSnapshot


class SandboxProvisionError(RuntimeError):
    """Raised when a sandbox cannot be provisioned or controlled."""


def _commands_enabled() -> bool:
    return os.getenv("ASTRAFORGE_EXECUTE_COMMANDS", "0").lower() in {"1", "true", "yes"}


def _env_flag(name: str, default: str | None = None) -> bool:
    value = os.getenv(name, default or "")
    return value.lower() in {"1", "true", "yes", "on"}


def _render_command(command: str | Sequence[str]) -> str:
    if isinstance(command, (list, tuple)):
        return shlex.join(str(part) for part in command)
    return str(command)


def _safe_volume_suffix(raw: str) -> str:
    """Return a Docker volume-safe suffix (alnum, underscore, dash, dot)."""
    allowed = []
    for char in raw:
        if char.isalnum() or char in {"_", "-", "."}:
            allowed.append(char)
        else:
            allowed.append("-")
    sanitized = "".join(allowed).strip("-") or "workspace"
    return sanitized.lower()


@dataclass
class SandboxRuntime:
    ref: str
    control_endpoint: str
    workspace_path: str


class SandboxOrchestrator:
    _CPU_CGROUP_PATHS = CPU_CGROUP_PATHS

    def __init__(self, runner: CommandRunner | None = None):
        self.runner = runner or CommandRunner(dry_run=not _commands_enabled())
        self._log = logging.getLogger(__name__)
        self._s3_client_cached = None
        self._s3_bucket = os.getenv("SANDBOX_S3_BUCKET", "").strip()
        self._s3_endpoint = os.getenv("SANDBOX_S3_ENDPOINT_URL") or os.getenv("AWS_ENDPOINT_URL")
        self._s3_region = os.getenv("SANDBOX_S3_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
        self._s3_use_ssl = (
            os.getenv("SANDBOX_S3_USE_SSL", "1").lower() not in {"0", "false", "no"}
        )
        self._snapshot_base_dir = os.getenv("SANDBOX_SNAPSHOT_DIR", "").rstrip("/")

    def _snapshot_dir(self, session: SandboxSession) -> str:
        """Return a per-session snapshot directory outside the workspace."""
        if self._snapshot_base_dir:
            return f"{self._snapshot_base_dir.rstrip('/')}/{session.id}"
        return f"/tmp/astraforge-snapshots/{session.id}"

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
        # Avoid exceeding OS argument limits by chunking the payload.
        # base64 uses [A-Za-z0-9+/=] so single-quoting is safe.
        chunk_size = 8000
        # Ensure directory exists and truncate the target file first.
        init_script = (
            f"mkdir -p {shlex.quote(directory)} && "
            f": > {shlex.quote(path)}"
        )
        result = self.execute(session, init_script)
        if result.exit_code != 0:
            return result
        # Append content in manageable chunks.
        for offset in range(0, len(encoded), chunk_size):
            chunk = encoded[offset : offset + chunk_size]
            append_script = f"echo '{chunk}' | base64 -d >> {shlex.quote(path)}"
            result = self.execute(session, append_script)
            if result.exit_code != 0:
                return result
        return result

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
        archive_dir = self._snapshot_dir(session)
        archive_path = f"{archive_dir}/{snapshot_id}.tar.gz"
        include = " ".join(shlex.quote(path) for path in include_paths)
        excludes = list(exclude_paths) if exclude_paths is not None else []
        excludes.append(archive_dir)
        exclude_clause = " ".join(f"--exclude={shlex.quote(pattern)}" for pattern in excludes)
        command = (
            f"mkdir -p {shlex.quote(archive_dir)} && "
            f"tar -czf {shlex.quote(archive_path)} {exclude_clause} {include}"
        ).strip()
        self._log.info(
            "Creating sandbox snapshot",
            extra={
                "session_id": str(session.id),
                "snapshot_id": str(snapshot_id),
                "label": label,
                "include_paths": include_paths,
                "exclude_paths": exclude_paths,
                "archive_path": archive_path,
            },
        )
        try:
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
                size_bytes=size_bytes,
                include_paths=include_paths,
                exclude_paths=exclude_paths,
                archive_path=archive_path,
            )
            if session.workspace and size_bytes:
                get_quota_service().record_storage_usage(session.workspace, size_bytes)
                self._increment_session_storage(session, size_bytes)
            try:
                self._upload_snapshot_to_s3(session, snapshot, archive_path)
            except SandboxProvisionError as exc:
                self._log.warning(
                    "Snapshot upload to object storage failed; keeping local archive only",
                    extra={
                        "session_id": str(session.id),
                        "snapshot_id": str(snapshot.id),
                        "bucket": self._s3_bucket,
                        "error": str(exc),
                    },
                )
            self._record_latest_snapshot(session, snapshot.id)
            session.mark_activity()
            self._log.info(
                "Sandbox snapshot created",
                extra={
                    "session_id": str(session.id),
                    "snapshot_id": str(snapshot.id),
                    "archive_path": archive_path,
                    "size_bytes": size_bytes,
                    "s3_bucket": self._s3_bucket,
                    "s3_key": snapshot.s3_key or "",
                },
            )
            return snapshot
        except Exception:
            self._log.exception(
                "Failed to create sandbox snapshot",
                extra={
                    "session_id": str(session.id),
                    "snapshot_id": str(snapshot_id),
                    "archive_path": archive_path,
                    "include_paths": include_paths,
                    "exclude_paths": exclude_paths,
                },
            )
            raise

    def restore_snapshot(self, session: SandboxSession, snapshot: SandboxSnapshot):
        """Extract a snapshot archive back into the sandbox workspace."""
        if not snapshot.archive_path and not snapshot.s3_key:
            raise SandboxProvisionError("Snapshot archive path is missing")

        archive_path = snapshot.archive_path or f"{self._snapshot_dir(session)}/{snapshot.id}.tar.gz"
        # Prefer S3 when a bucket is configured; fall back to an existing local archive inside the sandbox.
        content = None
        download_attempted = False
        if snapshot.s3_key and self._s3_client():
            download_attempted = True
            content = self._download_snapshot_from_s3(snapshot)
        if content:
            upload = self.upload_bytes(session, archive_path, content)
            if int(upload.exit_code) != 0:
                message = (upload.stdout or upload.stderr or "").strip() or "Snapshot upload failed"
                raise SandboxProvisionError(message)
        exists = self.execute(session, f"test -s {shlex.quote(archive_path)}")
        if exists.exit_code != 0:
            message = "Snapshot archive is missing or empty"
            if download_attempted and snapshot.s3_key:
                message = "Snapshot archive is unavailable in remote storage"
            raise SandboxProvisionError(message)

        workspace_root = (session.workspace_path or "/workspace").rstrip("/") or "/workspace"
        include_paths = snapshot.include_paths or []
        base_dir = "/"
        strip_components = 0
        if len(include_paths) == 1:
            included = str(include_paths[0] or "").rstrip("/") or workspace_root
            if os.path.abspath(included) == os.path.abspath(workspace_root):
                base_dir = workspace_root
                parts = [part for part in Path(workspace_root).parts if part not in {"", "/"}]
                strip_components = len(parts)

        command_parts = [
            "tar",
            "-xzf",
            shlex.quote(archive_path),
            "-C",
            shlex.quote(base_dir),
            "--no-same-owner",
            "--no-same-permissions",
            "--no-overwrite-dir",
            "-m",
            "--warning=no-unknown-keyword",
        ]
        if strip_components:
            command_parts.append(f"--strip-components={strip_components}")
        command = " ".join(command_parts)
        result = self.execute(session, command, cwd=session.workspace_path)
        if result.exit_code != 0:
            message = (result.stdout or result.stderr or "").strip() or "Snapshot restore failed"
            raise SandboxProvisionError(message)

        self._record_latest_snapshot(session, snapshot.id)
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
        if session.workspace and size_bytes:
            get_quota_service().record_storage_usage(session.workspace, size_bytes)
            self._increment_session_storage(session, size_bytes)
        session.mark_activity()
        return artifact

    def list_artifacts(self, session: SandboxSession):
        return session.artifacts.all()

    def list_snapshots(self, session: SandboxSession):
        return session.snapshots.all()

    def terminate(self, session: SandboxSession, *, reason: str | None = None):
        if session.status == SandboxSession.Status.TERMINATED:
            return

        measured_cpu_seconds: float | None = None
        if session.workspace:
            measured_cpu_seconds = self._sample_cpu_usage_seconds(session)

        if reason:
            metadata = dict(session.metadata or {})
            metadata["terminated_reason"] = reason
            session.metadata = metadata

        if session.mode == SandboxSession.Mode.DOCKER:
            ident = self._extract_ref(session.ref)
            if ident:
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

        started = session.created_at or timezone.now()
        ended = session.last_activity_at or timezone.now()
        fallback_duration = max(0.0, (ended - started).total_seconds())
        duration = (
            measured_cpu_seconds
            if measured_cpu_seconds is not None and measured_cpu_seconds > 0
            else fallback_duration
        )
        session.status = SandboxSession.Status.TERMINATED
        session.cpu_seconds = max(0.0, duration)
        fields = ["status", "cpu_seconds", "updated_at"]
        if reason:
            fields.append("metadata")
        session.save(update_fields=fields)
        if session.workspace:
            get_quota_service().record_sandbox_runtime(session.workspace, duration)

    # internal helpers -------------------------------------------------

    def _docker_network_args(self) -> list[str]:
        network = (os.getenv("SANDBOX_DOCKER_NETWORK") or "").strip()
        if network:
            return ["--network", network]
        return []

    def _docker_host_gateway_args(self) -> list[str]:
        if _env_flag("SANDBOX_DOCKER_HOST_GATEWAY", "0"):
            return ["--add-host", "host.docker.internal:host-gateway"]
        return []

    def _docker_tmpfs_args(self) -> list[str]:
        tmpfs_config = os.getenv(
            "SANDBOX_DOCKER_TMPFS", "/tmp:rw,nosuid,nodev;/run:rw,nosuid,nodev"
        )
        args: list[str] = []
        for entry in tmpfs_config.split(";"):
            entry = entry.strip()
            if entry:
                args.extend(["--tmpfs", entry])
        return args

    def _docker_security_args(self) -> list[str]:
        args = ["--cap-drop", "ALL", "--security-opt", "no-new-privileges:true"]
        seccomp_profile = os.getenv("SANDBOX_DOCKER_SECCOMP", "default").strip()
        if seccomp_profile:
            args.extend(["--security-opt", f"seccomp={seccomp_profile}"])
        pids_limit = os.getenv("SANDBOX_DOCKER_PIDS_LIMIT", "512").strip()
        if pids_limit:
            args.extend(["--pids-limit", pids_limit])
        if _env_flag("SANDBOX_DOCKER_READ_ONLY", "1"):
            args.append("--read-only")
            args.extend(self._docker_tmpfs_args())
        return args

    def _docker_user_args(self) -> list[str]:
        user = os.getenv("SANDBOX_DOCKER_USER", "").strip()
        return ["--user", user] if user else []

    def _docker_label_args(self, session: SandboxSession) -> list[str]:
        labels = {
            "astraforge.sandbox.session": str(session.id),
            "astraforge.sandbox.user": str(session.user_id),
        }
        args: list[str] = []
        for key, value in labels.items():
            if value:
                args.extend(["--label", f"{key}={value}"])
        return args

    def _spawn_docker(self, session: SandboxSession) -> SandboxRuntime:
        ident = f"sandbox-{session.id}"
        workspace_path = session.workspace_path or "/workspace"
        adopted = self._try_adopt_existing_container(
            ident, workspace_path, session_id=str(session.id)
        )
        if adopted:
            return adopted

        args = [
            "docker",
            "run",
            "-d",
            "--name",
            ident,
            "--hostname",
            ident,
        ]
        args.extend(self._docker_network_args())
        args.extend(self._docker_host_gateway_args())
        args.extend(self._docker_security_args())
        args.extend(self._docker_user_args())
        args.extend(self._docker_label_args(session))
        mount = self._workspace_volume_mount(session)
        if not mount and _env_flag("SANDBOX_DOCKER_READ_ONLY", "1"):
            # World-writable workspace tmpfs so the non-root sandbox user can write.
            mount = f"type=tmpfs,target={workspace_path},tmpfs-mode=1777"
        if mount:
            args.extend(["--mount", mount])
        if session.cpu:
            args.extend(["--cpus", session.cpu])
        if session.memory:
            args.extend(["-m", session.memory])
        args.extend([session.image, "sleep", "infinity"])
        try:
            self.runner.run(args, allow_failure=False)
        except subprocess.CalledProcessError as exc:  # pragma: no cover - surfaced upstream
            message = str(exc.output or exc)
            conflict = self._is_container_name_conflict(message, exit_code=getattr(exc, "returncode", None))
            if conflict:
                adopted = self._try_adopt_existing_container(
                    ident, workspace_path, session_id=str(session.id)
                )
                if adopted:
                    return adopted
                # Cleanup conflicting container and retry once.
                self.runner.run(["docker", "rm", "-f", ident], allow_failure=True)
                try:
                    self.runner.run(args, allow_failure=False)
                except subprocess.CalledProcessError as inner_exc:  # pragma: no cover - surfaced upstream
                    message = str(inner_exc.output or inner_exc)
                    if self._is_container_name_conflict(
                        message, exit_code=getattr(inner_exc, "returncode", None)
                    ):
                        adopted = self._try_adopt_existing_container(
                            ident, workspace_path, session_id=str(session.id)
                        )
                        if adopted:
                            return adopted
                    session.status = SandboxSession.Status.FAILED
                    session.error_message = message
                    session.save(update_fields=["status", "error_message", "updated_at"])
                    summary = session.error_message.strip() or "Docker workspace startup failed"
                    raise SandboxProvisionError(
                        f"Failed to provision Docker sandbox after retry: {summary}"
                    ) from inner_exc
            else:
                session.status = SandboxSession.Status.FAILED
                session.error_message = message
                session.save(update_fields=["status", "error_message", "updated_at"])
                summary = session.error_message.strip() or "Docker workspace startup failed"
                raise SandboxProvisionError(
                    f"Failed to provision Docker sandbox: {summary}"
                ) from exc
        running, detail = self._ensure_container_active(ident)
        if not running:
            self.runner.run(["docker", "rm", "-f", ident], allow_failure=True)
            session.status = SandboxSession.Status.FAILED
            session.error_message = (
                f"Docker sandbox container is not running: {detail or 'unknown state'}"
            )
            session.save(update_fields=["status", "error_message", "updated_at"])
            raise SandboxProvisionError(session.error_message)
        return SandboxRuntime(
            ref=f"docker://{ident}",
            control_endpoint=f"docker://{ident}",
            workspace_path=workspace_path,
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
        return self._split_ref(ref)[1].strip()

    def _k8s(self):
        return k8s_provisioner.from_env()

    def _build_download_url(self, session: SandboxSession, storage_path: str) -> str:
        base = session.artifact_base_url or os.getenv("SANDBOX_ARTIFACT_BASE_URL", "")
        if not base:
            return ""
        return base.rstrip("/") + "/" + storage_path.lstrip("/")

    def _workspace_volume_mount(self, session: SandboxSession) -> str | None:
        """Optionally attach a persistent Docker volume for the sandbox workspace."""
        mode = os.getenv("SANDBOX_DOCKER_VOLUME_MODE", "").strip().lower()
        if not mode:
            return None

        workspace_path = session.workspace_path or "/workspace"
        prefix = os.getenv("SANDBOX_DOCKER_VOLUME_PREFIX", "astraforge-sandbox-")

        if mode == "session":
            volume = f"{prefix}session-{_safe_volume_suffix(str(session.id))}"
        elif mode == "user":
            volume = f"{prefix}user-{_safe_volume_suffix(str(session.user_id))}"
        elif mode == "static":
            configured = os.getenv("SANDBOX_DOCKER_VOLUME_NAME", "")
            if not configured:
                return None
            volume = _safe_volume_suffix(configured)
            if prefix and not configured.startswith(prefix):
                volume = f"{prefix}{volume}"
        else:
            return None

        return f"type=volume,source={volume},target={workspace_path}"

    def _record_latest_snapshot(self, session: SandboxSession, snapshot_id: uuid.UUID) -> None:
        """Persist the latest snapshot pointer on the session for easy restore."""
        try:
            metadata = dict(session.metadata or {})
            metadata["latest_snapshot_id"] = str(snapshot_id)
            session.metadata = metadata
            session.save(update_fields=["metadata", "updated_at"])
        except Exception as exc:  # noqa: BLE001
            # Do not block snapshot/restore flows if metadata save fails.
            self._log.warning(
                "Failed to record latest snapshot metadata",
                extra={"session_id": str(session.id), "error": str(exc)},
            )

    # cpu metering ---------------------------------------------------

    def _sample_cpu_usage_seconds(self, session: SandboxSession) -> float | None:
        if getattr(self.runner, "dry_run", False):
            return None
        if not session.ref:
            return None
        mode, identifier = self._split_ref(session.ref)
        identifier = identifier.strip()
        if not identifier:
            return None
        payload: str | None = None
        try:
            if mode == SandboxSession.Mode.DOCKER:
                payload = self._collect_docker_cpu_payload(identifier)
            elif mode in {SandboxSession.Mode.KUBERNETES, "kubernetes"}:
                payload = self._collect_k8s_cpu_payload(identifier)
        except Exception as exc:  # noqa: BLE001
            self._log.warning(
                "Failed to sample CPU usage for sandbox %s (%s): %s",
                session.id,
                mode,
                exc,
            )
            return None
        if not payload:
            self._log.info(
                "CPU usage payload missing for sandbox %s (%s); falling back to wall-clock duration",
                session.id,
                mode,
            )
            return None
        seconds = self._parse_cpu_usage_payload(payload)
        if seconds is None:
            preview = payload.replace("\n", " ")[:200]
            reason = self._diagnose_cpu_payload(payload)
            self._log.info(
                "Unable to parse CPU usage payload for sandbox %s (%s); %s. payload=%s",
                session.id,
                mode,
                reason,
                preview,
            )
            self._log.debug(
                "Raw CPU payload for sandbox %s (%s):\n%s",
                session.id,
                mode,
                payload.rstrip(),
            )
            return None
        self._log.debug(
            "Sampled CPU usage for sandbox %s (%s): %.4f seconds",
            session.id,
            mode,
            seconds,
        )
        return seconds

    def _collect_docker_cpu_payload(self, identifier: str) -> str | None:
        if not identifier:
            return None
        script = self._cpu_probe_script()
        result = self.runner.run(
            ["docker", "exec", identifier, "sh", "-c", script],
            allow_failure=True,
        )
        if result.exit_code == 0 and result.stdout:
            return result.stdout
        self._log.warning(
            "CPU probe failed inside Docker sandbox %s (exit_code=%s, stdout=%s)",
            identifier,
            result.exit_code,
            (result.stdout or "").strip()[:120],
        )
        return None

    def _collect_k8s_cpu_payload(self, identifier: str) -> str | None:
        namespace, pod = self._split_k8s_identifier(identifier)
        provisioner = self._k8s()
        api = provisioner._ensure_api()
        script = self._cpu_probe_script()
        try:
            output = k8s_stream(
                api.connect_get_namespaced_pod_exec,
                name=pod,
                namespace=namespace or provisioner.namespace,
                command=["/bin/sh", "-c", script],
                stderr=False,
                stdin=False,
                stdout=True,
                tty=False,
            )
        except Exception as exc:  # noqa: BLE001
            self._log.warning("Failed to read CPU stats for pod %s: %s", identifier, exc)
            return None
        if not output:
            self._log.warning(
                "CPU probe returned no output for Kubernetes sandbox %s/%s",
                namespace or provisioner.namespace,
                pod,
            )
        return output

    def _cpu_probe_script(self) -> str:
        return build_cpu_probe_script(self._CPU_CGROUP_PATHS)

    @staticmethod
    def _parse_cpu_usage_payload(payload: str | None) -> float | None:
        return parse_cpu_usage_payload(payload)

    @staticmethod
    def _diagnose_cpu_payload(payload: str) -> str:
        if not payload:
            return "payload empty"
        lines = [line.rstrip() for line in payload.splitlines() if line.strip()]
        if not lines:
            return "payload only whitespace"
        header = lines[0]
        if not (header.startswith("__PATH:") and header.endswith("__")):
            return f"missing __PATH header sentinel (header='{header}')"
        path_hint = header[len("__PATH:") : -2].strip()
        body = "\n".join(lines[1:]).strip()
        if not path_hint:
            return "header missing cgroup path hint"
        if not body:
            return f"cgroup file {path_hint} returned no content"
        if path_hint.endswith("cpu.stat"):
            if not any(line.startswith(("usage_usec", "usage_us")) for line in body.splitlines()):
                return f"cgroup cpu.stat content missing usage counters ({path_hint})"
        else:
            first_line = body.splitlines()[0]
            try:
                float(first_line)
            except ValueError:
                return f"cgroup file {path_hint} did not return numeric usage (got '{first_line[:40]}')"
        return f"unrecognized format from {path_hint}"

    def _increment_session_storage(self, session: SandboxSession, bytes_delta: int) -> None:
        if not bytes_delta:
            return
        try:
            session.storage_bytes = max(
                0,
                int((session.storage_bytes or 0)) + int(bytes_delta),
            )
            session.save(update_fields=["storage_bytes", "updated_at"])
        except Exception as exc:  # noqa: BLE001
            self._log.warning(
                "Failed to update sandbox storage consumption",
                extra={"session_id": str(session.id), "error": str(exc)},
            )

    # s3 helpers ------------------------------------------------------

    def _s3_client(self):
        if not self._s3_bucket:
            return None
        if self._s3_client_cached:
            return self._s3_client_cached

        session = boto3.session.Session()
        self._s3_client_cached = session.client(
            "s3",
            endpoint_url=self._s3_endpoint,
            region_name=self._s3_region,
            use_ssl=self._s3_use_ssl,
            config=Config(s3={"addressing_style": "path"}),
        )
        return self._s3_client_cached

    def _snapshot_object_key(self, session: SandboxSession, snapshot_id: uuid.UUID) -> str:
        return f"snapshots/{session.id}/{snapshot_id}.tar.gz"

    def _read_file_from_sandbox(self, session: SandboxSession, path: str) -> bytes:
        base64_cmd = f"base64 < {shlex.quote(path)}"
        result = self.execute(session, base64_cmd)
        if result.exit_code != 0:
            message = (result.stdout or result.stderr or "").strip() or "Snapshot read failed"
            raise SandboxProvisionError(message)
        raw_b64 = (result.stdout or "").replace("\n", "").strip()
        try:
            return base64.b64decode(raw_b64.encode("ascii")) if raw_b64 else b""
        except Exception as exc:  # noqa: BLE001
            raise SandboxProvisionError("Unable to decode snapshot archive") from exc

    def _upload_snapshot_to_s3(
        self,
        session: SandboxSession,
        snapshot: SandboxSnapshot,
        archive_path: str,
    ) -> None:
        client = self._s3_client()
        if not client:
            return

        content = self._read_file_from_sandbox(session, archive_path)
        key = snapshot.s3_key or self._snapshot_object_key(session, snapshot.id)

        try:
            client.put_object(
                Bucket=self._s3_bucket,
                Key=key,
                Body=content,
                ContentType="application/gzip",
            )
        except (BotoCoreError, ClientError) as exc:
            raise SandboxProvisionError(f"Snapshot upload failed: {exc}") from exc

        snapshot.s3_key = key
        snapshot.save(update_fields=["s3_key"])
        self._log.debug(
            "Uploaded sandbox snapshot to s3",
            extra={
                "session_id": str(session.id),
                "snapshot_id": str(snapshot.id),
                "bucket": self._s3_bucket,
                "key": key,
            },
        )

    def _download_snapshot_from_s3(self, snapshot: SandboxSnapshot) -> bytes | None:
        client = self._s3_client()
        if not client or not snapshot.s3_key:
            return None
        try:
            response = client.get_object(Bucket=self._s3_bucket, Key=snapshot.s3_key)
            body = response.get("Body")
            return body.read() if body else b""
        except (BotoCoreError, ClientError) as exc:
            self._log.warning(
                "Snapshot download failed; falling back to existing archive if present",
                extra={
                    "snapshot_id": str(snapshot.id),
                    "bucket": self._s3_bucket,
                    "key": snapshot.s3_key,
                    "error": str(exc),
                },
            )
            return None

    def _is_container_name_conflict(self, message: str, exit_code: int | None = None) -> bool:
        """Detect Docker name conflicts robustly across daemon variants."""
        text = (message or "").lower()
        if exit_code == 125 and "already in use" in text:
            return True
        conflict_patterns = [
            r"container name.+already in use",
            r"already in use.+container name",
            r"conflict.*container name",
            r"you have to remove .* to be able to reuse that name",
            r"marked for removal",
        ]
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in conflict_patterns)

    def _parse_docker_bool(self, raw: str | None) -> bool | None:
        if raw is None:
            return None
        normalized = str(raw).strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
        return None

    def _inspect_container_state(self, ident: str) -> tuple[bool, str, str, int | None]:
        """Return (running, status, error, exit_code) for a Docker container."""
        inspect = self.runner.run(
            ["docker", "inspect", "-f", "{{json .State}}", ident],
            allow_failure=True,
        )
        if inspect.exit_code != 0:
            message = (inspect.stderr or inspect.stdout or "").strip()
            return False, "unknown", message, None
        raw_state = (inspect.stdout or "").strip()
        try:
            data = json.loads(raw_state or "{}")
        except Exception:
            return True, "running", "", None
        running = bool(data.get("Running"))
        status = str(data.get("Status") or "")
        error = str(data.get("Error") or "").strip()
        exit_code_raw = data.get("ExitCode")
        try:
            exit_code = int(exit_code_raw)
        except (TypeError, ValueError):
            exit_code = None
        return running, status, error, exit_code

    def _format_container_state(self, status: str, error: str, exit_code: int | None) -> str:
        parts = []
        if status:
            parts.append(f"status={status}")
        if exit_code is not None:
            parts.append(f"exit_code={exit_code}")
        if error:
            parts.append(error)
        return "; ".join(part for part in parts if part) or "container is not running"

    def _ensure_container_active(self, ident: str) -> tuple[bool, str]:
        """Start the container if needed and confirm it is running."""
        running, status, error, exit_code = self._inspect_container_state(ident)
        if running:
            return True, ""
        started = self.runner.run(["docker", "start", ident], allow_failure=True)
        if started.exit_code == 0:
            running, status, error, exit_code = self._inspect_container_state(ident)
            if running:
                return True, ""
            detail = self._format_container_state(status, error, exit_code)
            fallback = (started.stderr or started.stdout or "").strip()
            if fallback and fallback not in detail:
                detail = f"{detail}; {fallback}"
            # Mocked runners or daemon quirks may report an unknown state even after a successful start.
            if status == "unknown":
                return True, detail
            return False, detail
        detail = self._format_container_state(status, error, exit_code)
        fallback = (started.stderr or started.stdout or "").strip()
        if fallback and fallback not in detail:
            detail = f"{detail}; {fallback}"
        return False, detail

    def _try_adopt_existing_container(
        self, ident: str, workspace_path: str, session_id: str | None = None
    ) -> SandboxRuntime | None:
        """If a container with the target name already exists, reuse it instead of failing."""
        inspect = self.runner.run(
            [
                "docker",
                "inspect",
                "-f",
                '{{ index .Config.Labels "astraforge.sandbox.session" }}|{{ .State.Running }}',
                ident,
            ],
            allow_failure=True,
        )
        if inspect.exit_code != 0:
            return None
        raw_output = (inspect.stdout or "").strip()
        label_value = ""
        running_raw = ""
        if "|" in raw_output:
            label_part, running_part = raw_output.split("|", maxsplit=1)
            label_value = label_part.strip()
            running_raw = running_part.strip()
        else:
            parts = raw_output.split()
            if parts:
                label_value = parts[0].strip()
            if len(parts) > 1:
                running_raw = parts[-1].strip()
        if label_value in {"<no value>", "<nil>"}:
            label_value = ""
        if session_id and label_value and label_value != session_id:
            return None
        running_flag = self._parse_docker_bool(running_raw)
        if running_flag is False:
            started = self.runner.run(["docker", "start", ident], allow_failure=True)
            if started.exit_code != 0:
                return None
        running, _ = self._ensure_container_active(ident)
        if not running:
            return None
        return SandboxRuntime(
            ref=f"docker://{ident}",
            control_endpoint=f"docker://{ident}",
            workspace_path=workspace_path,
        )
