# AstraForge

AstraForge is an AI-driven DevOps orchestrator that converts natural language requests into
reviewed merge requests. It combines a modular Django backend, a modern React frontend, and
pluggable executors that coordinate LLM-powered agents inside isolated workspaces.

## Monorepo Layout

- `backend/` – Django REST Framework + Celery service with hexagonal architecture and provider
  registries.
- `frontend/` – React + shadcn/ui application with React Query state management and renderer registry.
- `shared/` – OpenAPI schema outputs and message contract packages.
- `docs/` – Architecture notes and ADRs.
- `infra/` – CI pipelines and deployment scaffolding.
- `opa/` – Example Gatekeeper/OPA policies.

## Getting Started

### Prerequisites

Install the git hooks so linting and security checks run automatically on commit:

```bash
pip install pre-commit
pre-commit install
```

### Backend

```bash
make install-deps  # creates backend/.venv and installs backend/frontend deps
source backend/.venv/bin/activate
cd backend
python manage.py migrate
python manage.py runserver
```

### Runner

```bash
docker build -t astraforge/codex-cli:latest backend/codex_cli_stub
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Open `http://localhost:5173` and create an account from the Register page, then sign in to access the dashboard.

### Docker Compose

Run database migrations, then launch the stack:

```bash
docker compose run --rm backend-migrate
docker compose up --build
```
For local Compose runs, authentication is disabled via `UNSAFE_DISABLE_AUTH=1`. Do not use this in production.

### Authentication API

- UI requests use secure session cookies with CSRF protection. Hit `POST /api/auth/register/` or `POST /api/auth/login/` from the frontend to establish a session, and `POST /api/auth/logout/` to end it. Retrieve the current user via `GET /api/auth/me/`.
- `GET /api/auth/csrf/` – fetch a CSRF cookie (required before posting from external clients).
- `POST /api/api-keys/` – create an API key (response includes the plaintext key once). Supply it via the `X-Api-Key` header for headless integrations.
- `DELETE /api/api-keys/{id}/` – revoke an API key.

The frontend stores the access token in local storage for subsequent API requests.


## Tooling

- `pre-commit` with Ruff, Black, mypy, and Gitleaks.
- GitHub Actions workflow for linting, testing, and image builds.
- Makefile shortcuts for local development.

See `docs/architecture.md` and `docs/adr/0001-initial-architecture.md` for additional details.
