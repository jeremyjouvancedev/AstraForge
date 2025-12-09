# Deploying to Portainer (TrueNAS)

GitHub Actions builds and publishes Docker images to GHCR so Portainer can pull them without running local builds. The recommended deployment is the bundled `astraforge` image, which serves the Django API and built Vite frontend on port `8001`. Legacy split images remain available if you need them for existing stacks. The workflow emits branch/tag/sha tags for every push and a `latest` tag from `main` for:

- `ghcr.io/<namespace>/astraforge` (backend API + Celery + built frontend, served together)
- `ghcr.io/<namespace>/astraforge-backend`
- `ghcr.io/<namespace>/astraforge-frontend`
- `ghcr.io/<namespace>/astraforge-llm-proxy`
- `ghcr.io/<namespace>/astraforge-codex-cli` (on-demand Codex workspace/sandbox base; pulled by the backend/worker)
- `ghcr.io/<namespace>/astraforge-sandbox` (pulled by the backend when it spawns sandbox containers; you don’t run it as a service)

Replace `<namespace>` with your GitHub username or org (lowercase) and keep the PAT scope to `read:packages` when pulling from Portainer.

## Portainer prerequisites

1. Create a GitHub PAT with `read:packages`.
2. In Portainer, go to *Registries* → *Add registry*, choose *GitHub Container Registry* with `ghcr.io` and supply your GitHub username + PAT.

## GitHub Actions setup (GHCR publishing)

1. In GitHub: *Settings → Actions → General → Workflow permissions* → choose **Read and write permissions** so `GITHUB_TOKEN` can push to GHCR.
2. If the org enforces package publishing restrictions, allow the repo to publish to GHCR (`ghcr.io/<owner>/astraforge-*`).
3. Ensure Actions are enabled for the repo/organization.
4. The CI workflow lives at `.github/workflows/ci.yaml`. Pushes to `main` (and tags/branches) build and push images; pull requests build only (no push). The Node cache uses `frontend/pnpm-lock.yaml`, so keep that lock file committed.

## Stack template (no reverse proxy needed)

Use this Portainer stack to keep everything on a private overlay network and expose the bundled app directly on host port `8081` (change as needed). Images live under `ghcr.io/jeremyjouvancedev/astraforge-*`; set hostnames and adjust environment values for your TrueNAS secrets:

```yaml
version: "3.9"
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-astraforge}
      POSTGRES_USER: ${POSTGRES_USER:-astraforge}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}
      POSTGRES_HOST: ${POSTGRES_HOST:-postgres}
      POSTGRES_PORT: ${POSTGRES_PORT:-5433}
    volumes:
      - ${POSTGRES_DATA_PATH:-/portainer/Files/Volumes/astraforge-postgres}:/var/lib/postgresql/data
    command: ["postgres", "-p", "5433"]
    networks:
      - astraforge

  redis:
    image: redis:7
    networks:
      - astraforge

  llm-proxy:
    image: ghcr.io/jeremyjouvancedev/astraforge-llm-proxy:latest
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY:?set OPENAI_API_KEY}
      LLM_MODEL: ${LLM_MODEL:-gpt-4o-mini}
    # Optional: expose if Codex workspaces use host-mapped proxy access. If you attach
    # workspaces to the stack network (see CODEX_WORKSPACE_NETWORK), you can omit this.
    ports:
      - "18080:8080"
    networks:
      - astraforge

  app-migrate:
    image: ghcr.io/jeremyjouvancedev/astraforge:latest
    command: python manage.py migrate
    environment:
      DATABASE_URL: ${DATABASE_URL:-postgres://${POSTGRES_USER:-astraforge}:${POSTGRES_PASSWORD:-astraforge}@${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5433}/${POSTGRES_DB:-astraforge}}
      REDIS_URL: ${REDIS_URL:-redis://redis:6379/0}
    depends_on:
      - postgres
      - redis
    networks:
      - astraforge

  app:
    image: ghcr.io/jeremyjouvancedev/astraforge:latest
    ports:
      - "8081:8001"
    environment:
      DATABASE_URL: ${DATABASE_URL:-postgres://${POSTGRES_USER:-astraforge}:${POSTGRES_PASSWORD:-astraforge}@${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5433}/${POSTGRES_DB:-astraforge}}
      REDIS_URL: ${REDIS_URL:-redis://redis:6379/0}
      EXECUTOR: ${EXECUTOR:-codex}
      RUN_LOG_STREAMER: ${RUN_LOG_STREAMER:-redis}
      CELERY_TASK_ALWAYS_EAGER: ${CELERY_TASK_ALWAYS_EAGER:-"0"}
      ASTRAFORGE_EXECUTE_COMMANDS: ${ASTRAFORGE_EXECUTE_COMMANDS:-1}
      CODEX_CLI_SKIP_PULL: ${CODEX_CLI_SKIP_PULL:-1}
      CODEX_WORKSPACE_IMAGE: ${CODEX_WORKSPACE_IMAGE:-ghcr.io/jeremyjouvancedev/astraforge-codex-cli:latest}
      CODEX_WORKSPACE_NETWORK: ${CODEX_WORKSPACE_NETWORK:-astraforge}
      CODEX_WORKSPACE_PROXY_URL: ${CODEX_WORKSPACE_PROXY_URL:-http://llm-proxy:8080}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      SANDBOX_IMAGE: ${SANDBOX_IMAGE:-ghcr.io/jeremyjouvancedev/astraforge-sandbox:latest}
      SECRET_KEY: ${SECRET_KEY:?set SECRET_KEY}
      ALLOWED_HOSTS: ${ALLOWED_HOSTS:-astraforge.example.com,api.astraforge.example.com}
      CSRF_TRUSTED_ORIGINS: ${CSRF_TRUSTED_ORIGINS:-http://astraforge.example.com,http://api.astraforge.example.com}
      OPENAI_API_KEY: ${OPENAI_API_KEY:?set OPENAI_API_KEY}
      # DeepAgent sandbox defaults (10 minutes idle, 1 hour max lifetime)
      SANDBOX_IDLE_TIMEOUT_SEC: ${SANDBOX_IDLE_TIMEOUT_SEC:-600}
      SANDBOX_MAX_LIFETIME_SEC: ${SANDBOX_MAX_LIFETIME_SEC:-3600}
    depends_on:
      - postgres
      - redis
      - app-migrate
      - llm-proxy
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    networks:
      astraforge:
        aliases:
          - astraforge
          - backend
          - frontend

  app-worker:
    image: ghcr.io/jeremyjouvancedev/astraforge:latest
    command: celery -A astraforge.config.celery_app worker --loglevel=info -Q astraforge.core,astraforge.default --beat
    environment:
      DATABASE_URL: ${DATABASE_URL:-postgres://${POSTGRES_USER:-astraforge}:${POSTGRES_PASSWORD:-astraforge}@${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5433}/${POSTGRES_DB:-astraforge}}
      REDIS_URL: ${REDIS_URL:-redis://redis:6379/0}
      EXECUTOR: ${EXECUTOR:-codex}
      RUN_LOG_STREAMER: ${RUN_LOG_STREAMER:-redis}
      CELERY_TASK_ALWAYS_EAGER: ${CELERY_TASK_ALWAYS_EAGER:-"0"}
      ASTRAFORGE_EXECUTE_COMMANDS: ${ASTRAFORGE_EXECUTE_COMMANDS:-1}
      CODEX_CLI_SKIP_PULL: ${CODEX_CLI_SKIP_PULL:-1}
      CODEX_WORKSPACE_IMAGE: ${CODEX_WORKSPACE_IMAGE:-ghcr.io/jeremyjouvancedev/astraforge-codex-cli:latest}
      CODEX_WORKSPACE_NETWORK: ${CODEX_WORKSPACE_NETWORK:-astraforge}
      CODEX_WORKSPACE_PROXY_URL: ${CODEX_WORKSPACE_PROXY_URL:-http://llm-proxy:8080}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      SANDBOX_IMAGE: ${SANDBOX_IMAGE:-ghcr.io/jeremyjouvancedev/astraforge-sandbox:latest}
      SECRET_KEY: ${SECRET_KEY:?set SECRET_KEY}
      ALLOWED_HOSTS: ${ALLOWED_HOSTS:-astraforge.example.com,api.astraforge.example.com}
      CSRF_TRUSTED_ORIGINS: ${CSRF_TRUSTED_ORIGINS:-http://astraforge.example.com,http://api.astraforge.example.com}
      OPENAI_API_KEY: ${OPENAI_API_KEY:?set OPENAI_API_KEY}
      # DeepAgent sandbox defaults (10 minutes idle, 1 hour max lifetime)
      SANDBOX_IDLE_TIMEOUT_SEC: ${SANDBOX_IDLE_TIMEOUT_SEC:-600}
      SANDBOX_MAX_LIFETIME_SEC: ${SANDBOX_MAX_LIFETIME_SEC:-3600}
    depends_on:
      - postgres
      - redis
      - app-migrate
      - llm-proxy
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    networks:
      - astraforge

networks:
  astraforge:
```

Notes:
- Postgres uses `pgvector/pgvector:pg16`, so the `vector` extension is available out of the box; run `CREATE EXTENSION IF NOT EXISTS vector;` in your init scripts if you add embeddings.
- The bundled `astraforge` image serves both the SPA assets and `/api` on port `8001` via Django + WhiteNoise; no separate frontend container or `BACKEND_ORIGIN` env var is required.
- Sandbox containers are still created on-demand by the backend (via `SANDBOX_IMAGE`, defaulting to the published `ghcr.io/<namespace>/astraforge-sandbox:latest`). Ensure your hosts/agents can pull from GHCR; you do **not** need to run the sandbox image as a long-lived service in the stack.
- Keep `ASTRAFORGE_EXECUTE_COMMANDS` unquoted (`1`, not `"1"`) so the sandbox runner executes real Docker commands instead of staying in dry-run mode.
- `CODEX_CLI_SKIP_PULL=1` assumes the sandbox image already exists on the host; unset or set to `0` if the host must pull from GHCR (and make sure `docker login ghcr.io` is in place for private images).
- Override `CODEX_WORKSPACE_IMAGE` if you want to pin a specific Codex CLI tag (default `ghcr.io/<namespace>/astraforge-codex-cli:latest`); leave pull enabled or pre-load the image when using `CODEX_CLI_SKIP_PULL=1`.
- Attach Codex workspaces to the stack network by setting `CODEX_WORKSPACE_NETWORK=astraforge` (or your stack network name); this lets them reach the LLM proxy at `http://llm-proxy:8080` without host port mapping. If you leave it blank, the workspace stays on the default bridge and you’ll need `llm-proxy` published (e.g., host port `18080`) or set `CODEX_WORKSPACE_PROXY_URL` to a reachable host/IP:port.
- Set `SECRET_KEY` to a strong value and adjust `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` for your domains.

### Deployment flow

1. Push to `main` to publish fresh `latest`/branch/SHA tags to GHCR (including the combined `astraforge` image).
2. In Portainer, create a new stack, paste the YAML above, and set env vars (`OPENAI_API_KEY`, optional `LLM_MODEL`, and any Django settings you override).
3. Deploy; Portainer will pull GHCR images, run migrations, and bring up the API/SPA, worker, and LLM proxy.
4. Update by re-deploying the stack with a new tag (e.g., a specific SHA) or letting it track `latest`.

Notes:
- Keep `/var/run/docker.sock` mounted for the backend/worker only if you rely on Docker-based workspace execution; remove it on clusters where that access is not allowed.
- Swap Postgres/Redis for external services if your TrueNAS already hosts them; update the URLs accordingly.
- Set DNS for `astraforge.example.com` (or your preferred hostname) to the TrueNAS/Portainer host so nginx can route traffic. Add TLS by mounting certs/keys and updating the nginx config with `listen 443 ssl` plus `ssl_certificate` / `ssl_certificate_key`.
