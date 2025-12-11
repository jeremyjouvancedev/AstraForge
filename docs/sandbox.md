# Sandbox Orchestrator

The sandbox API lets external agents launch and control secure desktops running in Docker (local speed) or Kubernetes (multi-tenant isolation). Sessions always use UUID identifiers and expose shell exec, file upload, snapshots, and heartbeats so callers can keep control over lifecycle and cleanup.

> Note: GUI controls (mouse/keyboard), screenshots, and live view streaming endpoints are in place but currently return `501 Not Implemented` until the sandbox daemon is wired in.

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

When using the deep agent proxy (`llm-proxy`), a convenience API exists:

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

- Create an internal-only bridge so sandboxes can talk to the AI gateway but not the internet: `docker network create --internal astraforge-sandbox`.
- Attach the AI gateway (`llm-proxy`) container to that network (Compose already does this) and set `SANDBOX_DOCKER_NETWORK=astraforge-sandbox` on the backend/worker.
- Security flags are enabled by default: `--read-only`, tmpfs mounts for `/workspace`, `/tmp`, and `/run`, `--cap-drop=ALL`, `--security-opt=no-new-privileges:true`, optional seccomp profile via `SANDBOX_DOCKER_SECCOMP`, and `--pids-limit` (512 by default). Disable them only if you explicitly need a writable rootfs or host gateway access (`SANDBOX_DOCKER_HOST_GATEWAY=0` by default).
- Writes still land in `/workspace` via a tmpfs mount when no volume is configured; the fallback tmpfs is world-writable (mode `1777`) so the non-root sandbox user can treat `/workspace` like its home. Set `SANDBOX_DOCKER_VOLUME_MODE` (`session`/`user`/`static`) when you need persistence. Override tmpfs targets with `SANDBOX_DOCKER_TMPFS=/tmp:rw,nosuid,nodev;/run:rw,nosuid,nodev`.
- If the sandbox must reach a different AI gateway, point `SANDBOX_DOCKER_NETWORK` at a bridge that exposes it, or set `CODEX_WORKSPACE_PROXY_URL` to an address reachable from that network.
- Package installs: Pip/npm/pnpm already work inside `/workspace`. To allow `apt-get`, run as root and drop the read-only flag: set `SANDBOX_DOCKER_READ_ONLY=0`, `SANDBOX_DOCKER_USER=root`, and attach to a network with internet egress (unset `SANDBOX_DOCKER_NETWORK` or create a non-internal bridge). Use host firewall rules on that bridge to block RFC1918 ranges if you want “internet-only” egress. Re-enable the hardened defaults after provisioning dependencies.

## Kubernetes mode (secure isolation)

- Export a kubeconfig reachable from the backend container (`PROVISIONER=k8s` and the hybrid override in `docker-compose.hybrid.yml` help when running API + worker via Compose).
- Optional envs: `KUBERNETES_SERVICE_ACCOUNT`, `ASTRAFORGE_K8S_NAMESPACE`, `KUBERNETES_WORKSPACE_TIMEOUT`.
- The orchestrator will create pods with the requested image and return `k8s://<namespace>/<pod>` references. Shell exec and uploads use `kubectl exec` under the hood.
- Sandboxes run with non-root user/group IDs, read-only root filesystems, dropped capabilities, `seccomp: RuntimeDefault`, and service account tokens disabled. Apply the `infra/k8s/local/workspace-networkpolicy.yaml` overlay (or equivalent in your cluster) to allow DNS + `llm-proxy` + internet while blocking RFC1918/link-local ranges (so NAS/LAN stays unreachable). Use the `workspace-networkpolicy-open.yaml` variant only if you need unrestricted egress.

## Artifacts and snapshots

- Snapshots currently write a tarball inside the sandbox (`/tmp/sandbox-<id>.tar.gz`). Hook an upload step to S3/MinIO from there to expose download URLs.
- `artifact_base_url` is stored on the session for downstream tools to persist signed URLs once an uploader is added.
- Set `SANDBOX_ARTIFACT_BASE_URL` (or per-session `artifact_base_url`) to mint `download_url` values for exported files; the sandbox path is appended to that base.

## Operational notes

- Idle and max-lifetime timeouts are stored per session (default idle timeout is 5 minutes); the heartbeat endpoint lets agents keep a session alive while streaming UI traffic elsewhere.
- A scheduled Celery beat task (`reap-sandbox-sessions`) runs every `SANDBOX_REAP_INTERVAL_SEC` seconds (default `60`) and automatically terminates sandboxes that have exceeded their `idle_timeout_sec` or `max_lifetime_sec` windows, issuing a `docker rm -f` for Docker-backed sessions and recording the reason in session metadata.
- All identifiers are UUIDs to avoid guessable numeric ids in URLs.
- The orchestrator shells into the runtime when no GUI daemon is present; swapping to a dedicated daemon later will not break the public API contract.
