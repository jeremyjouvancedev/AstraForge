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

Use this Portainer stack to keep everything on a private overlay network and expose the bundled app directly on host port `8081` (change as needed). It also wires an internal-only `astraforge-sandbox` network so sandbox containers can reach the AI gateway (`llm-proxy`) without full internet egress. Images live under `ghcr.io/jeremyjouvancedev/astraforge-*`; set hostnames and adjust environment values for your TrueNAS secrets:

```yaml
version: "3.9"
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-astraforge}
      POSTGRES_USER: ${POSTGRES_USER:-astraforge}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
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

  minio:
    image: minio/minio:latest
    command: server /data --console-address :9001
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-astraforge}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-astraforge123}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 5s
      timeout: 3s
      retries: 10
    volumes:
      - ${MINIO_DATA_PATH:-/portainer/Files/Volumes/astraforge-minio}:/data
    networks:
      - astraforge

  minio-setup:
    image: minio/mc:latest
    depends_on:
      - minio
    entrypoint: >
      /bin/sh -c "
      set -e;
      tries=0;
      until mc alias set local http://minio:9000 ${MINIO_ROOT_USER:-astraforge} ${MINIO_ROOT_PASSWORD:-astraforge123}; do
        tries=$$((tries+1));
        if [ $$tries -ge 30 ]; then echo 'MinIO not ready'; exit 1; fi;
        sleep 2;
      done;
      mc mb --ignore-existing local/${SANDBOX_S3_BUCKET:-astraforge-snapshots};
      "
    networks:
      - astraforge

  llm-proxy:
    image: ghcr.io/jeremyjouvancedev/astraforge-llm-proxy:latest
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      LLM_MODEL: ${LLM_MODEL:-gpt-4o-mini}
    # Optional: expose if Codex workspaces use host-mapped proxy access. If you attach
    # workspaces to the stack network (see CODEX_WORKSPACE_NETWORK), you can omit this.
    ports:
      - "18080:8080"
    networks:
      - astraforge
      - astraforge-sandbox

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
      SANDBOX_DOCKER_NETWORK: ${SANDBOX_DOCKER_NETWORK:-astraforge-sandbox}
      SANDBOX_DOCKER_READ_ONLY: ${SANDBOX_DOCKER_READ_ONLY:-1}
      SANDBOX_DOCKER_SECCOMP: ${SANDBOX_DOCKER_SECCOMP:-}
      SANDBOX_DOCKER_PIDS_LIMIT: ${SANDBOX_DOCKER_PIDS_LIMIT:-512}
      SANDBOX_DOCKER_USER: ${SANDBOX_DOCKER_USER:-}
      SANDBOX_IMAGE: ${SANDBOX_IMAGE:-ghcr.io/jeremyjouvancedev/astraforge-sandbox:latest}
      UNSAFE_DISABLE_AUTH: ${UNSAFE_DISABLE_AUTH:-"1"}
      SECRET_KEY: ${SECRET_KEY}
      ALLOWED_HOSTS: ${ALLOWED_HOSTS:-*}
      CSRF_TRUSTED_ORIGINS: ${CSRF_TRUSTED_ORIGINS:-http://host.docker.internal:8081,http://backend:8001}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      # DeepAgent sandbox defaults (10 minutes idle, 1 hour max lifetime)
      SANDBOX_IDLE_TIMEOUT_SEC: ${SANDBOX_IDLE_TIMEOUT_SEC:-600}
      SANDBOX_MAX_LIFETIME_SEC: ${SANDBOX_MAX_LIFETIME_SEC:-3600}
      SANDBOX_S3_BUCKET: ${SANDBOX_S3_BUCKET:-astraforge-snapshots}
      SANDBOX_S3_ENDPOINT_URL: ${SANDBOX_S3_ENDPOINT_URL:-http://minio:9000}
      SANDBOX_S3_REGION: ${SANDBOX_S3_REGION:-us-east-1}
      SANDBOX_S3_USE_SSL: ${SANDBOX_S3_USE_SSL:-0}
      AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:-astraforge}
      AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY:-astraforge123}
      AWS_DEFAULT_REGION: ${AWS_DEFAULT_REGION:-us-east-1}
    depends_on:
      - postgres
      - redis
      - minio-setup
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
      SANDBOX_DOCKER_NETWORK: ${SANDBOX_DOCKER_NETWORK:-astraforge-sandbox}
      SANDBOX_DOCKER_READ_ONLY: ${SANDBOX_DOCKER_READ_ONLY:-1}
      SANDBOX_DOCKER_SECCOMP: ${SANDBOX_DOCKER_SECCOMP:-}
      SANDBOX_DOCKER_PIDS_LIMIT: ${SANDBOX_DOCKER_PIDS_LIMIT:-512}
      SANDBOX_DOCKER_USER: ${SANDBOX_DOCKER_USER:-}
      SANDBOX_IMAGE: ${SANDBOX_IMAGE:-ghcr.io/jeremyjouvancedev/astraforge-sandbox:latest}
      UNSAFE_DISABLE_AUTH: ${UNSAFE_DISABLE_AUTH:-"1"}
      SECRET_KEY: ${SECRET_KEY}
      ALLOWED_HOSTS: ${ALLOWED_HOSTS:-*}
      CSRF_TRUSTED_ORIGINS: ${CSRF_TRUSTED_ORIGINS:-http://host.docker.internal:8081,http://backend:8001}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      # DeepAgent sandbox defaults (10 minutes idle, 1 hour max lifetime)
      SANDBOX_IDLE_TIMEOUT_SEC: ${SANDBOX_IDLE_TIMEOUT_SEC:-600}
      SANDBOX_MAX_LIFETIME_SEC: ${SANDBOX_MAX_LIFETIME_SEC:-3600}
      SANDBOX_S3_BUCKET: ${SANDBOX_S3_BUCKET:-astraforge-snapshots}
      SANDBOX_S3_ENDPOINT_URL: ${SANDBOX_S3_ENDPOINT_URL:-http://minio:9000}
      SANDBOX_S3_REGION: ${SANDBOX_S3_REGION:-us-east-1}
      SANDBOX_S3_USE_SSL: ${SANDBOX_S3_USE_SSL:-0}
      AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:-astraforge}
      AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY:-astraforge123}
      AWS_DEFAULT_REGION: ${AWS_DEFAULT_REGION:-us-east-1}
    depends_on:
      - postgres
      - redis
      - minio-setup
      - app-migrate
      - llm-proxy
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    networks:
      - astraforge

networks:
  astraforge:
  astraforge-sandbox:
    name: astraforge-sandbox
    internal: true
```

Notes:
- Portainer’s stack env interpolation does not support the `:?` “required var” guard. Set stack
  variables for `POSTGRES_PASSWORD`, `OPENAI_API_KEY`, and `SECRET_KEY` explicitly before deploying.
- Postgres uses `pgvector/pgvector:pg16`, so the `vector` extension is available out of the box; run `CREATE EXTENSION IF NOT EXISTS vector;` in your init scripts if you add embeddings.
- The bundled `astraforge` image serves both the SPA assets and `/api` on port `8001` via Django + WhiteNoise; no separate frontend container or `BACKEND_ORIGIN` env var is required.
- Sandbox containers are still created on-demand by the backend (via `SANDBOX_IMAGE`, defaulting to the published `ghcr.io/<namespace>/astraforge-sandbox:latest`). Ensure your hosts/agents can pull from GHCR; you do **not** need to run the sandbox image as a long-lived service in the stack.
- The internal `astraforge-sandbox` network is `internal: true`, so sandboxes only reach `llm-proxy` (and DNS). If you need a different AI gateway, attach it to that network or change `SANDBOX_DOCKER_NETWORK`.
- For dependency installation inside sandboxes, temporarily relax the hardening: set `SANDBOX_DOCKER_READ_ONLY=0`, optionally `SANDBOX_DOCKER_USER=root` (for `apt-get`), and point `SANDBOX_DOCKER_NETWORK` to a non-internal bridge with internet egress. Revert to the secure defaults afterward.
- To enforce “internet-only” egress for Docker sandboxes on a NAS, keep an internal bridge for normal runs; if you must switch to a routed bridge for installs, add host firewall rules that drop traffic from that bridge’s subnet to RFC1918/link-local ranges while allowing outbound to the internet.
- Docker recipe for internet-only (no LAN): create a dedicated bridge (e.g., `docker network create astraforge-sandbox-inet` without `--internal`), apply host firewall rules to deny 10/8, 172.16/12, 192.168/16, 100.64/10, 169.254/16, 127/8 from that bridge’s CIDR, and set `SANDBOX_DOCKER_NETWORK=astraforge-sandbox-inet` when you need outbound installs. Use the default internal `astraforge-sandbox` bridge the rest of the time.
- MinIO provides snapshot storage for sandbox backups. The stack bootstraps a bucket named `${SANDBOX_S3_BUCKET:-astraforge-snapshots}` and the app/worker use `SANDBOX_S3_ENDPOINT_URL` + AWS-style credentials to upload and restore snapshots. Set `SANDBOX_S3_USE_SSL=1` if you front MinIO with TLS. Ports are not exposed; access the console via `docker exec` or temporary port-forwarding if needed.
- Keep `ASTRAFORGE_EXECUTE_COMMANDS` unquoted (`1`, not `"1"`) so the sandbox runner executes real Docker commands instead of staying in dry-run mode.
- `CODEX_CLI_SKIP_PULL=1` assumes the sandbox image already exists on the host; unset or set to `0` if the host must pull from GHCR (and make sure `docker login ghcr.io` is in place for private images).
- Override `CODEX_WORKSPACE_IMAGE` if you want to pin a specific Codex CLI tag (default `ghcr.io/<namespace>/astraforge-codex-cli:latest`); leave pull enabled or pre-load the image when using `CODEX_CLI_SKIP_PULL=1`.
- Attach Codex workspaces to the stack network by setting `CODEX_WORKSPACE_NETWORK=astraforge` (or your stack network name); this lets them reach the LLM proxy at `http://llm-proxy:8080` without host port mapping. If you leave it blank, the workspace stays on the default bridge and you’ll need `llm-proxy` published (e.g., host port `18080`) or set `CODEX_WORKSPACE_PROXY_URL` to a reachable host/IP:port.
- Set `SECRET_KEY` to a strong value and adjust `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` for your domains.
- For local/Portainer dev where you call the backend from workspaces via API key, set `UNSAFE_DISABLE_AUTH=1` to bypass CSRF/session checks. Do **not** use this in production.

### Deployment flow

1. Push to `main` to publish fresh `latest`/branch/SHA tags to GHCR (including the combined `astraforge` image).
2. In Portainer, create a new stack, paste the YAML above, and set env vars (`OPENAI_API_KEY`, optional `LLM_MODEL`, and any Django settings you override).
3. Deploy; Portainer will pull GHCR images, run migrations, and bring up the API/SPA, worker, and LLM proxy.
4. Update by re-deploying the stack with a new tag (e.g., a specific SHA) or letting it track `latest`.

Notes:
- Keep `/var/run/docker.sock` mounted for the backend/worker only if you rely on Docker-based workspace execution; remove it on clusters where that access is not allowed.
- Swap Postgres/Redis for external services if your TrueNAS already hosts them; update the URLs accordingly.
- Set DNS for `astraforge.example.com` (or your preferred hostname) to the TrueNAS/Portainer host so nginx can route traffic. Add TLS by mounting certs/keys and updating the nginx config with `listen 443 ssl` plus `ssl_certificate` / `ssl_certificate_key`.
