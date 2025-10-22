# Repository Guidelines

## Project Structure & Module Organization
- `backend/` hosts the Django app (`astraforge/`) arranged by layer: `domain/`, `interfaces/`, `infrastructure/`, with pytest suites in `tests/` and commands via `manage.py`.
- `frontend/` is the Vite React client; author UI under `src/` and colocate Vitest specs in `tests/`.
- `shared/` stores the generated OpenAPI schema the backend emits; run `make generate-openapi` after API changes.
- `docs/`, `infra/`, and `opa/` capture architectural notes, IaC bundles, and Rego policies consumed in CI.

## Build, Test, and Development Commands
- `make install-deps` provisions the Python virtualenv and installs PNPM packages.
- `make backend-serve` starts Django on `http://localhost:8000`.
- `make frontend-dev` runs the Vite dev server on port `5173` with proxy defaults.
- `make test` chains `pytest` and `pnpm test -- --run`; use it before pushing.
- `pnpm build` packages the frontend, and `make generate-openapi` refreshes `shared/openapi/schema.yaml`.

## Coding Style & Naming Conventions
- Python: 4-space indent, `snake_case` for functions, `PascalCase` classes. Run `make lint` (Ruff check) and `make format` (Ruff formatter).
- TypeScript/React: prefer functional components, camelCase file names under `src/components/`, and Tailwind classes grouped semantically.
- Align shared DTOs with OpenAPI field casing and keep backend serializers and frontend clients in sync.

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
- Update `opa/` policies alongside feature work and document notable decisions in `docs/`.
