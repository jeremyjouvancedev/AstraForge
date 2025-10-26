.PHONY: backend-serve frontend-dev lint format test generate-openapi install-deps

backend-serve:
	cd backend && python manage.py runserver 0.0.0.0:8000

frontend-dev:
	cd frontend && pnpm dev

install-deps:
	cd backend && test -d .venv || python3 -m venv .venv
	cd backend && .venv/bin/pip install --upgrade pip
	cd backend && .venv/bin/pip install .[dev]
	cd frontend && pnpm install

lint:
	cd backend && ruff check .
	cd frontend && pnpm lint

format:
	cd backend && ruff format .
	cd frontend && pnpm lint --fix

test:
	cd backend && pytest
	cd frontend && pnpm test -- --run

generate-openapi:
	cd backend && python manage.py spectacular --file ../shared/openapi/schema.yaml
