# Contributing to AstraForge

Thank you for your interest in improving AstraForge! This guide explains how to get set up, propose changes, and ship high-quality updates.

## Ground rules
- Be kind and follow the [Code of Conduct](CODE_OF_CONDUCT.md).
- Keep docs in sync: update `docs/architecture.md` (mermaid diagram) and any relevant runbooks/ADRs when behavior changes.
- Maintain sandbox parity: changes to `backend/astraforge/sandbox/deepagent_backend.py` must also be applied to `astraforge-python-package/astraforge_toolkit/backend.py`.
- Keep the public site responsive and accessible.

## Getting started
1. Install dependencies:
   ```bash
   make install-deps
   ```
2. Create your `.env` (see `.env.example`) and start services for local dev:
   ```bash
   make backend-serve
   make frontend-dev
   ```
3. Run tests before pushing:
   ```bash
   make test               # pytest + pnpm test
   make lint               # Ruff + ESLint
   gitleaks detect --config gitleaks.toml
   ```

## Development tips
- Python: 4-space indents, snake_case functions, PascalCase classes. Use `make format` (Ruff formatter) before committing.
- TypeScript/React: functional components, camelCase filenames under `src/components`, colocate Vitest specs in `frontend/tests/`.
- Update OpenAPI when backend contracts change: `make generate-openapi`.
- Prefer `rg` for search; colocate tests near new behavior.

## Submitting changes
- Use imperative, ≤72 character commit subjects (e.g., `Add sandbox reaper alert`).
- Reference issues with `Refs #<id>` when applicable.
- Include screenshots or API diffs when UI or contract changes occur.
- Open a PR with a clear summary, local test results, and any rollout considerations (e.g., migrations, env vars).

## Security

If you discover a vulnerability, please follow the [Security Policy](SECURITY.md) instead of filing a public issue.
