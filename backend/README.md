# AstraForge Backend

This package is the Django + Celery service that powers AstraForge. Refer to the repository root
`README.md` for the full project overview and setup instructions.

## Setup

```bash
python -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.txt
```

Then run `python manage.py runserver` (or `make backend-serve` from the repo root).
