.PHONY: backend-serve frontend-dev frontend-build-image root-build-image lint format test compose-test generate-openapi install-deps package-build package-clean package-upload package-upload-test codex-image sandbox-image computer-use-image astra-control-image workspace-images build build-all up up-all down restart logs clean config

# Helper targets for local dev, container builds, and packaging.

COMPOSE ?= docker compose
COMPOSE_FILES ?= -f docker-compose.yml $(shell test -f docker-compose.override.yml && echo "-f docker-compose.override.yml")
COMPOSE_TEST_PROJECT ?= astraforge-test
COMPOSE_TEST_FILES ?= -f docker-compose.yml $(shell test -f docker-compose.override.yml && echo "-f docker-compose.override.yml") -f docker-compose.test.yml
FRONTEND_IMAGE ?= astraforge-frontend:local
ROOT_IMAGE ?= astraforge:local
CODEX_IMAGE ?= astraforge/codex-cli:latest
SANDBOX_IMAGE ?= astraforge/sandbox-daemon:latest
COMPUTER_USE_IMAGE ?= astraforge/computer-use:latest
ASTRA_CONTROL_IMAGE ?= astra-control:local

# Helper targets for local dev, container builds, and packaging.

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

# Build the desktop sandbox daemon image (with docker-compose override support).
sandbox-image:
	$(COMPOSE) $(COMPOSE_FILES) build sandbox-image

# Build the computer-use workspace image (with docker-compose override support).
computer-use-image:
	$(COMPOSE) $(COMPOSE_FILES) build computer-use-image

# Build the astra-control workspace image (with docker-compose override support).
astra-control-image:
	$(COMPOSE) $(COMPOSE_FILES) build astra-control-image

# Build all workspace images (uses docker-compose for override support).
workspace-images: computer-use-image astra-control-image sandbox-image

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

# ============================================================================
# Docker Compose Shortcuts (automatically uses docker-compose.override.yml)
# ============================================================================

# Build all services including workspace images (override file automatically applied)
build-all: computer-use-image astra-control-image sandbox-image
	$(COMPOSE) $(COMPOSE_FILES) build

# Build all services (override file automatically applied)
build:
	$(COMPOSE) $(COMPOSE_FILES) build

# Build specific service (e.g., make build-backend)
build-%:
	$(COMPOSE) $(COMPOSE_FILES) build $*

# Build all services without cache
build-clean:
	$(COMPOSE) $(COMPOSE_FILES) build --no-cache

# Build everything and start all services
up-all: build-all
	$(COMPOSE) $(COMPOSE_FILES) up -d

# Start all services
up:
	$(COMPOSE) $(COMPOSE_FILES) up -d

# Start all services with logs in foreground
up-logs:
	$(COMPOSE) $(COMPOSE_FILES) up

# Stop all services
down:
	$(COMPOSE) $(COMPOSE_FILES) down

# Stop and remove all volumes (WARNING: deletes data!)
down-volumes:
	$(COMPOSE) $(COMPOSE_FILES) down -v

# Restart all services
restart:
	$(COMPOSE) $(COMPOSE_FILES) restart

# Restart specific service (e.g., make restart-backend)
restart-%:
	$(COMPOSE) $(COMPOSE_FILES) restart $*

# View logs from all services
logs:
	$(COMPOSE) $(COMPOSE_FILES) logs -f

# View logs from specific service (e.g., make logs-backend)
logs-%:
	$(COMPOSE) $(COMPOSE_FILES) logs -f $*

# Show merged docker-compose configuration (verifies override applied)
config:
	$(COMPOSE) $(COMPOSE_FILES) config

# Show merged configuration for specific service
config-%:
	$(COMPOSE) $(COMPOSE_FILES) config $*

# Clean up containers, networks, and optionally volumes
clean:
	$(COMPOSE) $(COMPOSE_FILES) down
	docker system prune -f

# Full rebuild: stop, clean, rebuild, and start
rebuild: down build-clean up

# Show status of all services
ps:
	$(COMPOSE) $(COMPOSE_FILES) ps

# Execute shell in a running service (e.g., make shell-backend)
shell-%:
	$(COMPOSE) $(COMPOSE_FILES) exec $* /bin/bash

# Show help for available make targets
help:
	@echo "Available targets:"
	@echo ""
	@echo "Docker Compose (uses docker-compose.override.yml automatically):"
	@echo "  make build-all          - Build ALL (services + workspace images)"
	@echo "  make up-all             - Build ALL and start all services"
	@echo "  make build              - Build all services"
	@echo "  make build-backend      - Build specific service"
	@echo "  make build-clean        - Build without cache"
	@echo "  make up                 - Start all services (detached)"
	@echo "  make up-logs            - Start all services (with logs)"
	@echo "  make down               - Stop all services"
	@echo "  make down-volumes       - Stop and remove volumes (deletes data!)"
	@echo "  make restart            - Restart all services"
	@echo "  make restart-backend    - Restart specific service"
	@echo "  make logs               - View logs from all services"
	@echo "  make logs-backend       - View logs from specific service"
	@echo "  make config             - Show merged docker-compose config"
	@echo "  make config-backend     - Show config for specific service"
	@echo "  make clean              - Clean up containers and networks"
	@echo "  make rebuild            - Full rebuild (stop, clean, rebuild, start)"
	@echo "  make ps                 - Show status of all services"
	@echo "  make shell-backend      - Open shell in running service"
	@echo ""
	@echo "Development:"
	@echo "  make backend-serve      - Run Django dev server locally"
	@echo "  make frontend-dev       - Run Vite dev server locally"
	@echo "  make install-deps       - Install Python and Node.js dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  make test               - Run all tests locally"
	@echo "  make backend-test       - Run backend tests"
	@echo "  make frontend-test      - Run frontend tests"
	@echo "  make compose-test       - Run tests in containers"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint               - Lint backend and frontend"
	@echo "  make format             - Format backend and frontend code"
	@echo ""
	@echo "Images:"
	@echo "  make workspace-images   - Build workspace images (uses docker-compose override)"
	@echo "  make computer-use-image - Build computer-use workspace image"
	@echo "  make astra-control-image - Build astra-control workspace image"
	@echo "  make sandbox-image      - Build sandbox daemon image (uses docker-compose override)"
	@echo "  make codex-image        - Build Codex CLI image"
	@echo ""
	@echo "Package:"
	@echo "  make package-build      - Build Python package"
	@echo "  make package-clean      - Clean package artifacts"
	@echo "  make package-upload     - Upload to PyPI"
	@echo ""
