## Sandbox Session Lifecycle

This document captures how sandbox sessions are created, reused, and restored across the backend API and the Python toolkit.

### Creation and reuse
- API endpoint: `POST /api/sandbox/sessions/`.
- Supplying an `id` pins the session to that UUID for the same user. If it already exists and is ready, the endpoint returns `200` and skips provisioning; otherwise it provisions/restores under the same id.
- Docker containers are named `sandbox-{session_id}` so concurrent calls for the same session target the same container. The orchestrator will adopt an existing container when possible; if the container is in a “marked for removal” state, it cleans up and retries.
- The Python toolkit accepts both `200` (reuse) and `201` (create) responses. If the API returns `404` during creation, it retries without the pinned id. If the second `404` is caused by a corrupted snapshot (tar/gzip errors), it drops `restore_snapshot_id` and provisions a fresh session.

### Runtime selection
- Docker is the default mode; Kubernetes is supported via `mode: "k8s"`. Session refs look like `docker://sandbox-<uuid>` or `k8s://<namespace/pod>`.
- CPU/memory limits and custom users propagate to the runtime, and labels include the session and user IDs for targeting and cleanup.

### Auto-restore and readiness
- Requests that need a session call `_ensure_session_ready` (backend viewset and toolkit). If the session is not ready, it provisions and restores the latest snapshot (if recorded in session metadata).
- Expired, failed, or terminated sessions trigger recreation. Expired sessions reuse `metadata.latest_snapshot_id` when available.
- Status polling waits for “ready”; if a session stays “starting” past the configured timeout, a new session is created.

### Snapshots and artifacts
- Snapshot archives default to `/tmp/astraforge-snapshots/{session_id}/{snapshot_id}.tar.gz`; override with `SANDBOX_SNAPSHOT_DIR`. The snapshot directory itself is excluded from the tarball.
- Snapshots are created on-demand via `POST /api/sandbox/sessions/{id}/snapshot` (and `/snapshots`), automatically before explicit stops/deletes (label `auto-stop`), and by the reaper before idle/lifetime terminations (labels `auto-idle_timeout` / `auto-max_lifetime`).
- On creation, the latest snapshot ID is stored in session metadata for transparent reuse. Restores prefer S3 when configured and fall back to the on-disk archive; missing or corrupted archives fail before extraction.
- Tar extraction uses safe flags (`--no-same-owner`, `--no-same-permissions`, `--no-overwrite-dir`, strip components when restoring to `/workspace`).
- Artifact exports base64 the file from inside the sandbox and mint a `download_url` when `SANDBOX_ARTIFACT_BASE_URL` (or per-session `artifact_base_url`) is set; otherwise the API streams bytes directly.

### Toolkit behavior (astraforge_toolkit)
- Respects a pinned session id from `configurable.sandbox_session_id` or `session_params["id"]`.
- Retries creation after 404 (drops pinned id), and if the retry also returns 404 due to a bad snapshot, retries without `restore_snapshot_id` to get a clean workspace.
- Handles binary file downloads gracefully: returns bytes by default; when decoding, falls back to replacement characters if the content is not valid UTF-8.
- Auto-restores the latest snapshot when recreating expired/failed sessions.

### Key environment variables
- `SANDBOX_SNAPSHOT_DIR`: Optional base directory for snapshot archives (default `/tmp/astraforge-snapshots`).
- `SANDBOX_S3_BUCKET`, `SANDBOX_S3_ENDPOINT_URL`, `SANDBOX_S3_REGION`, `SANDBOX_S3_USE_SSL`: Enable snapshot upload/download to object storage.
- `SANDBOX_DOCKER_VOLUME_MODE`, `SANDBOX_DOCKER_READ_ONLY`, `SANDBOX_DOCKER_USER`, `SANDBOX_DOCKER_NETWORK`, `SANDBOX_DOCKER_SECCOMP`, `SANDBOX_DOCKER_PIDS_LIMIT`: Control Docker runtime behavior.
- `idle_timeout_sec` / `max_lifetime_sec`: Set per session; the reaper terminates sessions that exceed idle or lifetime windows, recording `terminated_reason` in metadata.
