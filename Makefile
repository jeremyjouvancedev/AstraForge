.PHONY: backend-serve frontend-dev lint format test generate-openapi install-deps package-build package-clean package-upload package-upload-test

backend-serve:
	cd backend && python manage.py runserver 0.0.0.0:8000

frontend-dev:
	cd frontend && pnpm dev

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
	cd backend && pytest
	cd frontend && pnpm test -- --run

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
