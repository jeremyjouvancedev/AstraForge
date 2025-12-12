# Docker Compose Runbook

Use Docker Compose whenever you want the entire AstraForge stack (Postgres, Redis,
MinIO, API, Celery worker, LLM proxy, and frontend) running with a single command. This guide walks
through prepping environment variables, building images, and managing the lifecycle of the stack
defined in `docker-compose.yml`.

## Prerequisites

- Docker Engine and Docker Compose plugin (v2.20+ recommended)
- Access to an OpenAI-compatible key for the LLM proxy
- Port availability: `5433`, `6379`, `8001`, `8081`, `5174`
- Persistent data: Postgres uses a named volume (`postgres-data`) so accounts/API keys survive restarts.

## 1. Set up environment variables

Create a `.env` file in the repo root so the `backend`, `backend-worker`, and
`llm-proxy` services can read secrets and feature flags. At minimum you need the
LLM credentials; you can override any other values shown in
`docker-compose.yml`.

```bash
cat <<'ENV' > .env
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
UNSAFE_DISABLE_AUTH=1   # keep this to skip login locally
CODEX_CLI_SKIP_PULL=1   # prevents redundant image pulls
CODEX_WORKSPACE_IMAGE=ghcr.io/jeremyjouvancedev/astraforge-codex-cli:latest
SANDBOX_IMAGE=ghcr.io/jeremyjouvancedev/astraforge-sandbox:latest
SANDBOX_DOCKER_SECCOMP= # leave empty if your Docker daemon lacks the built-in "default" seccomp profile
ENV
```

> The compose file already wires the Postgres/Redis URLs. Only add overrides if
> you need different ports, credentials, or log verbosity.

Because `CODEX_CLI_SKIP_PULL=1` is set in `docker-compose.yml`, you must pull the
workspace and sandbox images before running migrations:

```bash
docker pull "$CODEX_WORKSPACE_IMAGE"
docker pull "$SANDBOX_IMAGE"
```

MinIO (plus a bootstrap job) runs alongside Postgres/Redis so sandbox snapshots
have object storage; keep the default credentials in `.env` for local runs or
override them if you already have a MinIO/S3 endpoint.

## 2. Build images and apply migrations

Run database migrations inside the application container before bringing the
stack online:

```bash
docker compose run --rm backend-migrate
```

This builds the backend image, waits for Postgres/Redis, and executes
`python manage.py migrate` so the DB schema matches the current code.

## 3. Launch the stack

Bring everything up (API, worker, frontend, and LLM proxy) with hot reloads by
mounting the repository into each service:

```bash
docker compose up --build
```

- Backend API → http://localhost:8001
- Frontend → http://localhost:5174 (proxying to the backend service)
- LLM Proxy → http://localhost:8081

On subsequent runs you can skip `--build` unless dependencies changed.

## 4. Manage the lifecycle

| Task | Command |
| --- | --- |
| View status | `docker compose ps` |
| Follow logs for a service | `docker compose logs -f backend` |
| Recreate a single container | `docker compose up --build backend` |
| Stop the stack | `docker compose down` |
| Stop and reset volumes | `docker compose down -v` |

The backend and worker containers mount `/var/run/docker.sock`. Make sure your
local Docker daemon is running and accessible, otherwise agents will fail to
spawn workspaces.

## Troubleshooting

- **Migrations keep running** – Ensure Postgres finished booting (watch
  `docker compose logs -f postgres`) before rerunning `backend-migrate`.
- **LLM proxy fails to start** – Confirm `OPENAI_API_KEY` is set in `.env`; the
  proxy refuses to boot otherwise.
- **Port already in use** – Stop conflicting local services or override the
  `ports` entries in `docker-compose.yml`.
- **File permission issues on Linux** – add your user to the `docker` group so
  the mounted Docker socket remains writable.
- **Seccomp profile error (`open default: no such file`)** – Some Docker
  installs do not ship the built-in `default` seccomp profile. Set
  `SANDBOX_DOCKER_SECCOMP=` (empty) in `.env` to skip the flag, or point it to a
  real profile file. See Docker’s seccomp guide:
  https://docs.docker.com/engine/security/seccomp/

With these steps you can stand up AstraForge end-to-end in just a few minutes
and iterate locally without juggling multiple terminal windows.
