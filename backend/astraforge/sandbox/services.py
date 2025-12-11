from __future__ import annotations

import base64
import logging
import os
import re
import shlex
import subprocess
import uuid
from dataclasses import dataclass
from typing import Optional, Sequence

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from astraforge.infrastructure.provisioners import k8s as k8s_provisioner
from astraforge.infrastructure.workspaces.codex import CommandRunner
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
        base_workspace = (session.workspace_path or "/workspace").rstrip("/") or "/workspace"
        archive_dir = f"{base_workspace}/.sandbox-snapshots"
        archive_path = f"{archive_dir}/{snapshot_id}.tar.gz"
        include = " ".join(shlex.quote(path) for path in include_paths)
        excludes = list(exclude_paths) if exclude_paths is not None else []
        excludes.append(archive_dir)
        exclude_clause = " ".join(f"--exclude={shlex.quote(pattern)}" for pattern in excludes)
        command = (
            f"mkdir -p {shlex.quote(archive_dir)} && "
            f"tar -czf {shlex.quote(archive_path)} {exclude_clause} {include}"
        ).strip()
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
        return snapshot

    def restore_snapshot(self, session: SandboxSession, snapshot: SandboxSnapshot):
        """Extract a snapshot archive back into the sandbox workspace."""
        if not snapshot.archive_path and not snapshot.s3_key:
            raise SandboxProvisionError("Snapshot archive path is missing")

        archive_path = snapshot.archive_path or f"/tmp/{snapshot.id}.tar.gz"
        # Prefer S3 when a bucket is configured; fall back to an existing local archive inside the sandbox.
        content = None
        if snapshot.s3_key and self._s3_client():
            content = self._download_snapshot_from_s3(snapshot)
        if content:
            upload = self.upload_bytes(session, archive_path, content)
            if int(upload.exit_code) != 0:
                message = (upload.stdout or upload.stderr or "").strip() or "Snapshot upload failed"
                raise SandboxProvisionError(message)

        command = (
            "tar "
            "-xzf "
            f"{shlex.quote(archive_path)} "
            "-C / "
            "--no-same-owner --no-same-permissions --no-overwrite-dir -m "
            "--warning=no-unknown-keyword"
        )
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
        session.mark_activity()
        return artifact

    def list_artifacts(self, session: SandboxSession):
        return session.artifacts.all()

    def list_snapshots(self, session: SandboxSession):
        return session.snapshots.all()

    def terminate(self, session: SandboxSession, *, reason: str | None = None):
        if session.status == SandboxSession.Status.TERMINATED:
            return

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

        session.status = SandboxSession.Status.TERMINATED
        fields = ["status", "updated_at"]
        if reason:
            fields.append("metadata")
        session.save(update_fields=fields)

    # internal helpers -------------------------------------------------

    def _docker_network_args(self) -> list[str]:
        network = os.getenv("SANDBOX_DOCKER_NETWORK") or os.getenv("CODEX_WORKSPACE_NETWORK")
        if network:
            return ["--network", network]
        return ["--network", "none"]

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
        ident = f"sandbox-{str(session.id).replace('-', '')}"
        self.runner.run(["docker", "rm", "-f", ident], allow_failure=True)

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
        workspace_path = session.workspace_path or "/workspace"
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
        ]
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in conflict_patterns)

    def _try_adopt_existing_container(
        self, ident: str, workspace_path: str, session_id: str | None = None
    ) -> SandboxRuntime | None:
        """If a container with the target name already exists, reuse it instead of failing."""
        inspect = self.runner.run(
            [
                "docker",
                "inspect",
                "-f",
                '{{ index .Config.Labels "astraforge.sandbox.session" }} {{ .State.Running }}',
                ident,
            ],
            allow_failure=True,
        )
        if inspect.exit_code != 0:
            return None
        label_value, running_state = "", ""
        parts = inspect.stdout.strip().split()
        if parts:
            label_value = parts[0]
            running_state = parts[1] if len(parts) > 1 else ""
        if session_id and label_value and label_value != session_id:
            return None
        if running_state.lower() not in {"true", "running"}:
            started = self.runner.run(["docker", "start", ident], allow_failure=True)
            if started.exit_code != 0:
                return None
        return SandboxRuntime(
            ref=f"docker://{ident}",
            control_endpoint=f"docker://{ident}",
            workspace_path=workspace_path,
        )
