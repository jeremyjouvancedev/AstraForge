# Global Rules

- Always keep up to date docs/architecture.md on the root repo with the architecture in mermaid format
- Ensure the public website stays fully responsive and follows solid UX principles

# Repository Guidelines

## Project Structure & Module Organization
- `backend/` hosts the Django app (`astraforge/`) arranged by layer: `domain/`, `interfaces/`, `infrastructure/`, with pytest suites in `tests/` and commands via `manage.py`.
- `frontend/` is the Vite React client; author UI under `src/` and colocate Vitest specs in `tests/`.
- `docs/` and `infra/` capture architectural notes and IaC bundles consumed in CI.

## Build, Test, and Development Commands
- `make install-deps` provisions the Python virtualenv and installs PNPM packages.
- `make backend-serve` starts Django on `http://localhost:8001`.
- `make frontend-dev` runs the Vite dev server on port `5174` with proxy defaults.
- `make test` chains `pytest` and `pnpm test -- --run`; use it before pushing.
- `make compose-test` spins up Postgres/Redis via docker compose with test overrides (no host ports, isolated project/volumes for a clean DB), forces CODEX_CLI_SKIP_PULL=0, waits for Postgres readiness, runs backend/frontend tests in containers, then tears everything down.
- `pnpm build` packages the frontend, and `make generate-openapi` refreshes the OpenAPI schema after API changes.

## Coding Style & Naming Conventions
- Python: 4-space indent, `snake_case` for functions, `PascalCase` classes. Run `make lint` (Ruff check) and `make format` (Ruff formatter).
- TypeScript/React: prefer functional components, camelCase file names under `src/components/`, and Tailwind classes grouped semantically.
- Align shared DTOs with OpenAPI field casing and keep backend serializers and frontend clients in sync.
- Always use the OpenAI developer documentation MCP server if you need to work with the OpenAI API, ChatGPT Apps SDK, Codex,… without me having to explicitly ask.
- Always use langchain MCP server if you need to work with Langchain, Langgraph

## Testing Guidelines
- Backend tests sit in `backend/astraforge/tests/` and follow `test_*.py`; extend fixtures instead of hitting live services.
- Frontend specs live in `frontend/tests/` using Vitest + React Testing Library; name files `*.test.ts[x]`.
- Cover new behavior with unit or integration tests and ensure `make test` passes before review.

## Commit & Pull Request Guidelines
- Use imperative, ≤72 character subjects, e.g., `Add application service guard`, with rationale in the body if context is not obvious.
- Reference issues using `Refs #<id>` in commits and PR descriptions.
- PRs should call out functional impact, list local test results, and attach screenshots or API diffs when UI or contract changes.

## Security & Configuration Tips
- Run `gitleaks detect --config gitleaks.toml` before pushing to avoid secret leaks.
- `SELF_HOSTED` defaults to `true` for the open-source experience (billing UI + quota enforcement off); set `SELF_HOSTED=false` for hosted/SaaS behavior.
- When changing backend modules that are exposed via the published Python package, mirror the change
  in the export surface (SDK/code automation/deepagent) and docs so the package stays in sync.
- Keep the standalone Python package (`astraforge-python-package/`) in parity with backend logic:
  updates to `backend/astraforge/sandbox/deepagent_backend.py` must be reflected in
  `astraforge-python-package/astraforge_toolkit/backend.py` (and regenerate docs/readme).
- Sandbox backend parity is mandatory: `backend/astraforge/sandbox/deepagent_backend.py` and
  `astraforge-python-package/astraforge_toolkit/backend.py` must keep identical behavior and
  semantics (path resolution, create-only writes, edit/grep/read outputs), differing only by
  transport. Any change to one requires applying the same behavior to the other and updating tests
  and docs to reflect the shared contract.
