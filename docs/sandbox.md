# Sandbox Orchestrator

The sandbox API lets external agents launch and control secure desktops running in Docker (local speed) or Kubernetes (multi-tenant isolation). Sessions always use UUID identifiers and expose shell exec, file upload, snapshots, and heartbeats so callers can keep control over lifecycle and cleanup.

> Note: GUI controls (mouse/keyboard), screenshots, and live view streaming endpoints are in place but currently return `501 Not Implemented` until the sandbox daemon is wired in.

## Session lifecycle and reuse

- `POST /api/sandbox/sessions` reuses a supplied `id` for the same user; ready sessions return `200` without re-provisioning, otherwise the orchestrator provisions and restores the latest snapshot (tracked in session metadata).
- Docker containers are named `sandbox-{session_id}` with labels for session/user IDs. Existing containers are adopted when possible; if a container is “marked for removal,” the orchestrator cleans it up and retries.
- Sessions marked `failed`, `terminated`, or expired (`expires_at`) are recreated and restored from `metadata.latest_snapshot_id` when available. Readiness polling waits for `ready`; if a session remains `starting` past the timeout, a fresh session is created.
- Idle and max-lifetime timeouts are enforced per session (`idle_timeout_sec`, `max_lifetime_sec`). The heartbeat endpoint bumps timers without executing code, and a scheduled reaper terminates sandboxes that exceed either window, recording `terminated_reason` and capturing a best-effort snapshot first.
- Toolkit recovery: the Python client accepts `200/201` creation responses, retries after a `404` without the pinned id, and if a second `404` is caused by a corrupted snapshot, retries without `restore_snapshot_id` to return a clean workspace.

## API surface

- `POST /api/sandbox/sessions` – create a session. Body:

```json
{
  "mode": "docker",                    // or "k8s"
  "image": "astraforge/codex-cli:latest",
  "cpu": "1",                         // optional Docker --cpus constraint
  "memory": "2Gi",                    // optional Docker -m constraint
  "ephemeral_storage": "5Gi",         // reserved for future runtime classes
  "restore_snapshot_id": null,
  "idle_timeout_sec": 300,
  "max_lifetime_sec": 3600
}
```

Response includes `id`, `ref` (`docker://…` or `k8s://namespace/pod`), `control_endpoint`, and the current `status` (ready/failed/terminated).

- `POST /api/sandbox/sessions/{id}/exec` – run a shell command inside the sandbox.
- `POST /api/sandbox/sessions/{id}/upload` – write a file. Body fields: `path`, `content`, `encoding` (`utf-8` or `base64`).
- `POST /api/sandbox/sessions/{id}/snapshot` – create a tarball of the workspace (returns the in-guest archive path).
- `POST /api/sandbox/sessions/{id}/heartbeat` – bump idle timers without executing code.
- `DELETE /api/sandbox/sessions/{id}` – terminate and cleanup the container/pod.

Authentication matches the rest of the API (session auth or API keys). All sessions are scoped to the authenticated user.

A convenience API exists for DeepAgent conversations (the Codex-only `llm-proxy` is not required for these sandboxes):

- `POST /deepagent/conversations` – creates a sandbox session via the Django API and returns `{ conversation_id, sandbox_session_id, status }`. The IDs are aligned so one sandbox is used per conversation.
- `POST /deepagent/conversations/{conversation_id}/messages` – sends messages to a DeepAgents-based LangGraph agent configured with a `SandboxBackend` so filesystem tools, a Python REPL, a shell helper, Playwright browser helpers, image viewers, and Tavily web search all operate inside the associated sandbox. Pass `{"stream": true}` to receive a `text/event-stream` stream of JSON chunks (model tokens, tool calls, artifacts, etc.). The agent also understands `sandbox:workspace/...` Markdown links, which the backend and UI turn into downloadable file links.

## Docker mode (fast local)

- Set `ASTRAFORGE_EXECUTE_COMMANDS=1` and optionally `SANDBOX_IMAGE` to choose the desktop image.
- Start the stack with Docker Compose: `docker compose up backend backend-worker` (database/redis are already in the base file).
- Build a desktop-ready sandbox image (Xvfb + Fluxbox + non-root user) with `docker build -f sandbox/Dockerfile -t astraforge/sandbox-daemon:latest .` and set `SANDBOX_IMAGE=astraforge/sandbox-daemon:latest`.
- Create a session:

```bash
curl -X POST http://localhost:8001/api/sandbox/sessions \
  -H "X-Api-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"mode":"docker","image":"astraforge/codex-cli:latest"}'
```

Exec into it:

```bash
curl -X POST http://localhost:8001/api/sandbox/sessions/<id>/exec \
  -H "X-Api-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"command":"ls -la","cwd":"/workspace"}'
```

### Hardened Docker sandboxes

- Create an internal-only bridge to isolate sandboxes from the internet: `docker network create --internal astraforge-sandbox`. DeepAgent sandboxes do not need the Codex LLM proxy, so you can leave this bridge empty unless you explicitly expose another gateway.
- If you want Codex workloads on the same bridge to reach the proxy, attach the `llm-proxy` container (Compose already does this for Codex) and set `SANDBOX_DOCKER_NETWORK=astraforge-sandbox` on the backend/worker.
- Security flags are enabled by default: `--read-only`, tmpfs mounts for `/workspace`, `/tmp`, and `/run`, `--cap-drop=ALL`, `--security-opt=no-new-privileges:true`, optional seccomp profile via `SANDBOX_DOCKER_SECCOMP`, and `--pids-limit` (512 by default). Disable them only if you explicitly need a writable rootfs or host gateway access (`SANDBOX_DOCKER_HOST_GATEWAY=0` by default).
- Writes still land in `/workspace` via a tmpfs mount when no volume is configured; the fallback tmpfs is world-writable (mode `1777`) so the non-root sandbox user can treat `/workspace` like its home. Set `SANDBOX_DOCKER_VOLUME_MODE` (`session`/`user`/`static`) when you need persistence. Override tmpfs targets with `SANDBOX_DOCKER_TMPFS=/tmp:rw,nosuid,nodev;/run:rw,nosuid,nodev`.
- If Codex needs a different AI gateway, point `SANDBOX_DOCKER_NETWORK` at a bridge that exposes it, or set `CODEX_WORKSPACE_PROXY_URL` to an address reachable from that network.
- Package installs: Pip/npm/pnpm already work inside `/workspace`. To allow `apt-get`, run as root and drop the read-only flag: set `SANDBOX_DOCKER_READ_ONLY=0`, `SANDBOX_DOCKER_USER=root`, and attach to a network with internet egress (unset `SANDBOX_DOCKER_NETWORK` or create a non-internal bridge). Use host firewall rules on that bridge to block RFC1918 ranges if you want “internet-only” egress. Re-enable the hardened defaults after provisioning dependencies.

## Kubernetes mode (secure isolation)

- Export a kubeconfig reachable from the backend container (`PROVISIONER=k8s` and the hybrid override in `docker-compose.hybrid.yml` help when running API + worker via Compose).
- Optional envs: `KUBERNETES_SERVICE_ACCOUNT`, `ASTRAFORGE_K8S_NAMESPACE`, `KUBERNETES_WORKSPACE_TIMEOUT`.
- The orchestrator will create pods with the requested image and return `k8s://<namespace>/<pod>` references. Shell exec and uploads use `kubectl exec` under the hood.
- Sandboxes run with non-root user/group IDs, read-only root filesystems, dropped capabilities, `seccomp: RuntimeDefault`, and service account tokens disabled. Apply the `infra/k8s/local/workspace-networkpolicy.yaml` overlay (or equivalent in your cluster) to allow DNS + public internet while blocking RFC1918/link-local ranges (so NAS/LAN stays unreachable); Codex pods layer the `codex-egress-llm-proxy` policy when they need the in-cluster proxy, while DeepAgent sandboxes stay proxy-free. Use the `workspace-networkpolicy-open.yaml` variant only if you need unrestricted egress.

## Artifacts and snapshots

- Snapshots write archives to `/tmp/astraforge-snapshots/{session_id}/{snapshot_id}.tar.gz` by default; override with `SANDBOX_SNAPSHOT_DIR`. The snapshot directory itself is excluded from the tarball, and the latest snapshot ID is tracked in session metadata for transparent reuse.
- Restores prefer S3/MinIO when `SANDBOX_S3_BUCKET` (and related vars) is set; otherwise they use the on-disk archive. Missing or corrupted archives fail before extraction. Tar extraction uses safe flags (`--no-same-owner`, `--no-same-permissions`, `--no-overwrite-dir`, strip components when restoring to `/workspace`).
- Snapshots are taken (1) on-demand via `POST /api/sandbox/sessions/{id}/snapshot` or `/snapshots`, (2) automatically before an explicit stop/delete (`DELETE /api/sandbox/sessions/{id}` or `/stop`, labeled `auto-stop`), and (3) by the reaper before terminating idle/expired sessions (labeled `auto-idle_timeout` or `auto-max_lifetime`).
- `artifact_base_url` is stored on the session for downstream tools to persist signed URLs once an uploader is added.
- Set `SANDBOX_ARTIFACT_BASE_URL` (or per-session `artifact_base_url`) to mint `download_url` values for exported files; the sandbox path is appended to that base.

## Operational notes

- Idle and max-lifetime timeouts are stored per session (default idle timeout is 5 minutes); the heartbeat endpoint lets agents keep a session alive while streaming UI traffic elsewhere. Activity (exec/upload/snapshot) updates `last_activity_at`/`last_heartbeat_at`.
- A scheduled Celery beat task (`reap-sandbox-sessions`) runs every `SANDBOX_REAP_INTERVAL_SEC` seconds (default `60`) and automatically terminates sandboxes that have exceeded their `idle_timeout_sec` or `max_lifetime_sec` windows, issuing a `docker rm -f` for Docker-backed sessions and recording the reason in session metadata.
- All identifiers are UUIDs to avoid guessable numeric ids in URLs.
- The orchestrator shells into the runtime when no GUI daemon is present; swapping to a dedicated daemon later will not break the public API contract.
