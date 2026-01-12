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

## Ollama (local host access)

If you're running Ollama on your laptop and need containers to reach it, install
it from https://ollama.com/download, pull the model you plan to use (default
`devstral-small-2:24b`), then start the server:

```bash
ollama pull devstral-small-2:24b
OLLAMA_HOST=0.0.0.0 ollama serve
```
