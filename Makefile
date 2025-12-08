.PHONY: backend-serve frontend-dev lint format test compose-test generate-openapi install-deps package-build package-clean package-upload package-upload-test

COMPOSE ?= docker compose
COMPOSE_TEST_PROJECT ?= astraforge-test
COMPOSE_TEST_FILES ?= -f docker-compose.yml -f docker-compose.test.yml

backend-serve:
	cd backend && python manage.py runserver 0.0.0.0:8001

frontend-dev:
	cd frontend && pnpm dev

backend-test:
	cd backend && pytest

frontend-test:
	cd frontend && pnpm test -- --run --watch=false

install-deps:
	cd backend && test -d .venv || python3 -m venv .venv
	cd backend && .venv/bin/pip install --upgrade pip
	cd backend && .venv/bin/pip install -r requirements-dev.txt
	cd frontend && pnpm install

lint:
	cd backend && ruff check .
	cd frontend && pnpm lint

format:
	cd backend && ruff format .
	cd frontend && pnpm lint --fix

test:
	$(MAKE) backend-test
	$(MAKE) frontend-test

compose-test:
	$(COMPOSE) $(COMPOSE_TEST_FILES) -p $(COMPOSE_TEST_PROJECT) up -d postgres redis
	$(COMPOSE) $(COMPOSE_TEST_FILES) -p $(COMPOSE_TEST_PROJECT) exec -T postgres sh -c 'until pg_isready -U "$${POSTGRES_USER:-astraforge}" -h localhost -p 5433; do sleep 1; done'
	$(COMPOSE) $(COMPOSE_TEST_FILES) -p $(COMPOSE_TEST_PROJECT) run --rm --no-deps -e CODEX_CLI_SKIP_PULL=0 backend python -m pytest
	$(COMPOSE) $(COMPOSE_TEST_FILES) -p $(COMPOSE_TEST_PROJECT) run --rm --no-deps frontend pnpm test -- --run --watch=false
	$(COMPOSE) $(COMPOSE_TEST_FILES) -p $(COMPOSE_TEST_PROJECT) down -v

generate-openapi:
	cd backend && python manage.py spectacular --file ../shared/openapi/schema.yaml

package-build:
	cd astraforge-python-package && python -m build

package-clean:
	rm -rf astraforge-python-package/dist astraforge-python-package/build astraforge-python-package/*.egg-info

package-upload-test:
	@if [ ! -f "$$HOME/.pypirc" ] && [ -z "$$TWINE_PASSWORD" ]; then \
		echo "Provide TWINE_PASSWORD or a ~/.pypirc with testpypi credentials"; exit 1; \
	fi
	cd astraforge-python-package && TWINE_USERNAME=$${TWINE_USERNAME:-__token__} python -m twine upload --repository testpypi dist/*

package-upload:
	@if [ ! -f "$$HOME/.pypirc" ] && [ -z "$$TWINE_PASSWORD" ]; then \
		echo "Provide TWINE_PASSWORD or a ~/.pypirc with pypi credentials"; exit 1; \
	fi
	cd astraforge-python-package && TWINE_USERNAME=$${TWINE_USERNAME:-__token__} python -m twine upload dist/*
