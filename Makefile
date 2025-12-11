.PHONY: backend-serve frontend-dev frontend-build-image root-build-image lint format test compose-test generate-openapi install-deps package-build package-clean package-upload package-upload-test codex-image sandbox-image workspace-images

# Helper targets for local dev, container builds, and packaging.

COMPOSE ?= docker compose
COMPOSE_TEST_PROJECT ?= astraforge-test
COMPOSE_TEST_FILES ?= -f docker-compose.yml -f docker-compose.test.yml
FRONTEND_IMAGE ?= astraforge-frontend:local
ROOT_IMAGE ?= astraforge:local
CODEX_IMAGE ?= astraforge/codex-cli:latest
SANDBOX_IMAGE ?= astraforge/sandbox-daemon:latest

# Run the Django dev server on 0.0.0.0:8001 (local code, no container).
backend-serve:
	cd backend && python manage.py runserver 0.0.0.0:8001

# Start the Vite dev server with hot reload.
frontend-dev:
	cd frontend && pnpm dev

# Build only the frontend production image (nginx-based).
frontend-build-image:
	docker build -t $(FRONTEND_IMAGE) -f frontend/Dockerfile frontend

# Build the bundled root image (backend + built frontend) from the repo root.
root-build-image:
	docker build -t $(ROOT_IMAGE) -f Dockerfile .

# Build the Codex CLI workspace image used by the executor.
codex-image:
	docker build -t $(CODEX_IMAGE) backend/codex_cli_stub

# Build the desktop sandbox daemon image.
sandbox-image:
	docker build -f sandbox/Dockerfile -t $(SANDBOX_IMAGE) .

workspace-images: codex-image sandbox-image

# Run backend unit tests via pytest.
backend-test:
	cd backend && pytest

# Run frontend unit tests via Vitest (CI-style).
frontend-test:
	cd frontend && pnpm test -- --run --watch=false

# Provision Python venv and install backend + frontend deps.
install-deps:
	cd backend && test -d .venv || python3 -m venv .venv
	cd backend && .venv/bin/pip install --upgrade pip
	cd backend && .venv/bin/pip install -r requirements-dev.txt
	cd frontend && pnpm install

# Lint backend (ruff) and frontend (pnpm lint).
lint:
	cd backend && ruff check .
	cd frontend && pnpm lint

# Format backend (ruff) and auto-fix frontend lint issues.
format:
	cd backend && ruff format .
	cd frontend && pnpm lint --fix

# Run both backend and frontend test suites locally.
test:
	$(MAKE) backend-test
	$(MAKE) frontend-test

# Bring up db/redis, run backend+frontend tests in containers, then tear down.
compose-test:
	$(COMPOSE) $(COMPOSE_TEST_FILES) -p $(COMPOSE_TEST_PROJECT) build backend frontend
	$(COMPOSE) $(COMPOSE_TEST_FILES) -p $(COMPOSE_TEST_PROJECT) up -d postgres redis minio minio-setup
	$(COMPOSE) $(COMPOSE_TEST_FILES) -p $(COMPOSE_TEST_PROJECT) exec -T postgres sh -c 'until pg_isready -U "$${POSTGRES_USER:-astraforge}" -h localhost -p 5433; do sleep 1; done'
	$(COMPOSE) $(COMPOSE_TEST_FILES) -p $(COMPOSE_TEST_PROJECT) run --rm --no-deps -e CODEX_CLI_SKIP_PULL=0 backend python -m pytest
	$(COMPOSE) $(COMPOSE_TEST_FILES) -p $(COMPOSE_TEST_PROJECT) run --rm --no-deps frontend pnpm test -- --run --watch=false
	$(COMPOSE) $(COMPOSE_TEST_FILES) -p $(COMPOSE_TEST_PROJECT) down -v

# Regenerate OpenAPI schema (outputs to repo root).
generate-openapi:
	cd backend && python manage.py spectacular --file ../openapi-schema.yaml

# Build the standalone Python package (astraforge-python-package/dist).
package-build:
	cd astraforge-python-package && python -m build

# Clean built artifacts for the Python package.
package-clean:
	rm -rf astraforge-python-package/dist astraforge-python-package/build astraforge-python-package/*.egg-info

# Upload package to TestPyPI (requires TWINE_PASSWORD or ~/.pypirc).
package-upload-test:
	@if [ ! -f "$$HOME/.pypirc" ] && [ -z "$$TWINE_PASSWORD" ]; then \
		echo "Provide TWINE_PASSWORD or a ~/.pypirc with testpypi credentials"; exit 1; \
	fi
	cd astraforge-python-package && TWINE_USERNAME=$${TWINE_USERNAME:-__token__} python -m twine upload --repository testpypi dist/*

# Upload package to PyPI (requires TWINE_PASSWORD or ~/.pypirc).
package-upload:
	@if [ ! -f "$$HOME/.pypirc" ] && [ -z "$$TWINE_PASSWORD" ]; then \
		echo "Provide TWINE_PASSWORD or a ~/.pypirc with pypi credentials"; exit 1; \
	fi
	cd astraforge-python-package && TWINE_USERNAME=$${TWINE_USERNAME:-__token__} python -m twine upload dist/*
