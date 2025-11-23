# AstraForge

![home](./images/astra_forge_home.jpg)
![diff](./images/astra_forge_diff_view.jpg)
![log](./images/astra_forge_log_view.jpg)

AstraForge is an AI-driven DevOps orchestrator that turns natural language requests into reviewed,
merge-ready pull requests. A Django + Celery backend coordinates agents running inside isolated
Codex workspaces, while a fully responsive React UI streams live run logs, diffs, and chat updates.

## Why AstraForge

- **Prompt-to-MR workflow** – Capture user intent, queue executions, and stream every run state
  change, artifact, and diff back to reviewers in real time.
- **Modular execution engine** – Swappable executors, provisioners, and provider registries keep the
  orchestration layer flexible enough for multiple LLM backends and VCS targets.
- **Observability built in** – Event streams, structured run logs, and diff previews keep operators
  informed before a branch ever lands in CI.
- **Collaborative review surface** – Chat with the agent during a run, inspect MR context, and hand
  off changes with confidence using generated summaries and metadata.

See `docs/architecture.md` for the current high-level diagram (kept in mermaid format) plus ADRs that
capture decisions as the system evolves.

## Monorepo Layout

```
.
├── backend/            # Django REST Framework API, Celery workers, provider registries
│   └── astraforge/
│       ├── domain/     # Pure domain models + repositories
│       ├── application/# Use-cases + orchestration pipelines
│       ├── interfaces/ # REST, SSE, registries, inbound adapters
│       └── infrastructure/ # ORM, Redis, external service adapters
├── frontend/           # Vite + React Query + shadcn/ui client
├── shared/             # Generated OpenAPI schema and DTO packages
├── llm-proxy/          # FastAPI wrapper that proxies OpenAI (or compatible) APIs
├── docs/               # Architecture overview, ADRs, runbooks
├── infra/              # Deployment scaffolding (docker, k8s, CI)
├── opa/                # OPA/Gatekeeper policies enforced in CI
└── images/             # Marketing and README screenshots
```

## Prerequisites

- Python `>= 3.11`, `pip`, and `virtualenv`
- Node.js `>= 20` with `pnpm` (the repo uses a lockfile)
- Docker + Docker Compose for local provisioning
- `make`, `pre-commit`, and `gitleaks`
- Access to an OpenAI-compatible API key for the LLM proxy

Install git hooks once so linting and leak scans run before each commit:

```bash
pip install pre-commit
pre-commit install
```

## Local Development (manual workflow)

1. **Install dependencies**

   ```bash
   make install-deps  # creates backend/.venv, installs backend + frontend deps
   ```

2. **Configure environment**

   Create a `.env` in the repo root (or export variables) covering the values used in
   `docker-compose.yml`, for example:

   ```bash
   cat <<'ENV' > .env
   DATABASE_URL=postgres://astraforge:astraforge@localhost:5432/astraforge
   REDIS_URL=redis://localhost:6379/0
   EXECUTOR=codex
   PROVISIONER=docker
   RUN_LOG_STREAMER=redis
   ASTRAFORGE_EXECUTE_COMMANDS=1
   UNSAFE_DISABLE_AUTH=1   # only for local dev
   CODEX_CLI_SKIP_PULL=1
   LOG_LEVEL=DEBUG
   OPENAI_API_KEY=sk-...
   LLM_MODEL=gpt-4o-mini
   ENV
   ```

3. **Migrate the database**

   ```bash
   source backend/.venv/bin/activate
   cd backend
   python manage.py migrate
   ```

4. **Run the backend API and Celery worker**

   ```bash
   # Terminal 1 – Django API
   make backend-serve

   # Terminal 2 – Celery worker queues
   cd backend
   celery -A astraforge.config.celery_app worker --loglevel=info -Q astraforge.core,astraforge.default
   ```

5. **Launch the LLM proxy**

   ```bash
   cd llm-proxy
   uvicorn app.main:app --reload --port 8080
   ```

6. **Build the Codex CLI runner stub** (used when a published image is unavailable)

   ```bash
   docker build -t astraforge/codex-cli:latest backend/codex_cli_stub
   ```

7. **Start the frontend**

   ```bash
   cd frontend
   pnpm dev
   ```

   Visit `http://localhost:5173`, register an account, and sign in. Authentication is disabled locally
   when `UNSAFE_DISABLE_AUTH=1`.

## Docker Compose Workflow

Prefer Compose when you want the entire stack (Postgres, Redis, API, worker, LLM proxy, frontend)
running with a single command:

```bash
docker compose run --rm backend-migrate
docker compose up --build
```

The compose file mounts the repo for hot reloads and shares the Docker socket so workspaces can spin
up isolated containers. Never ship with `UNSAFE_DISABLE_AUTH=1`; it is only for local testing.
For a full walkthrough (env setup, lifecycle commands, troubleshooting), see `docs/docker-compose.md`.

## Local Kubernetes Workflow

Need to validate the Kubernetes provisioner or mirror a client cluster? Use the
manifests under `infra/k8s/local` and follow `docs/kubernetes-local.md`.

At a high level you will:

1. Build the backend/worker, frontend, LLM proxy, and Codex workspace images (`backend/codex_cli_stub`).
2. Load those images into Kind/k3d/Minikube (e.g., `kind load docker-image astraforge/backend:local`).
3. Create the namespace + `astraforge-llm` secret, then `kubectl apply -k infra/k8s/local`.
4. Port-forward `svc/frontend` and `svc/backend` so the UI and API stay reachable at
   `http://localhost:5173` and `http://localhost:8000`.

Prefer a hybrid approach where the API and Celery worker remain in Docker Compose but
Codex workspaces run in Kubernetes? Generate a Docker-friendly kubeconfig
(`kind get kubeconfig … | sed 's/0.0.0.0/host.docker.internal/g' > ~/.kube/config-hybrid`),
export `HYBRID_KUBECONFIG=config-hybrid`, then start the stack with the override:

```bash
docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up backend backend-worker
```

The override mounts `~/.kube`, sets `PROVISIONER=k8s`, and injects `host.docker.internal` so
the containers can talk to your laptop’s cluster while the rest of the services keep using
Compose. See `docs/kubernetes-local.md` for the full walkthrough.

## Testing & Quality Gates

- `make lint` – Ruff + ESLint
- `make format` – Ruff formatter + ESLint `--fix`
- `make test` – `pytest` plus `pnpm test -- --run`
- `gitleaks detect --config gitleaks.toml` – secret scanning before pushes
- `make generate-openapi` – refresh `shared/openapi/schema.yaml` after API contract changes

## Useful Commands

| Task | Command |
| --- | --- |
| Install toolchains | `make install-deps` |
| Run API locally | `make backend-serve` |
| Run Celery worker | `celery -A astraforge.config.celery_app worker --loglevel=info -Q astraforge.core,astraforge.default` |
| Start frontend | `make frontend-dev` or `pnpm dev` |
| Build production assets | `pnpm build` |
| Generate OpenAPI | `make generate-openapi` |
| Refresh screenshots/docs | `docs/architecture.md`, `docs/adr/*` |

## Additional Resources

- `docs/architecture.md` – the canonical mermaid diagram plus subsystem explanations.
- `docs/docker-compose.md` – runbook for starting/stopping the stack with Docker Compose.
- `docs/adr/` – decision records that explain trade-offs.
- `infra/` – Dockerfiles, Helm charts, and CI definitions.
- `opa/` – Rego policies enforced before merges or deployments.

## Target Error Remediation Flow

Incoming exceptions from the deployed UI/API are captured by Glitchtip or Sentry, normalized, then
forwarded into the Codex execution pipeline so fixes ship with the right context (stack trace,
request metadata, and workspace snapshot). The workflow below shows the target automated loop:

```mermaid
flowchart LR
    App[Frontend / Backend Services]
    Glitchtip[Glitchtip]
    Sentry[Sentry]
    Router[Error Router Webhook]
    Prompt[Codex Prompt Builder]
    Queue[Run Queue]
    Workspace[Codex Workspace]
    Review[Merge Request & Notifications]

    App --> Glitchtip
    App --> Sentry
    Glitchtip -->|Stacktrace + metadata| Router
    Sentry -->|Stacktrace + metadata| Router
    Router --> Prompt
    Prompt -->|context-rich prompt| Queue
    Queue --> Workspace
    Workspace -->|patch + tests| Review
```

See `docs/architecture.md` for the accompanying narrative plus operational considerations when
wiring the observability stack into automated remediation.

## Roadmap

### Engine

- [ ] Add claude code
- [ ] Add Kimi Cli
- [ ] Add Open Coder
- [ ] Add Gemini Coder

### Feature

- [ ] Can choose base default docker image
- [ ] Can batch modify
- [ ] Can generate documentation
- [ ] Can generate architecture mindmap
- [ ] Add context7 mcp (for documentation latest version knowledge)
- [ ] Add playwright mcp to launch and test the App
