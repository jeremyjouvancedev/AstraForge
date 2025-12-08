# Deploying to Portainer (TrueNAS)

GitHub Actions now builds and publishes Docker images to GHCR so Portainer can pull them without running local builds. The workflow emits branch/tag/sha tags for every push and a `latest` tag from `main` for:

- `ghcr.io/<namespace>/astraforge-backend`
- `ghcr.io/<namespace>/astraforge-frontend`
- `ghcr.io/<namespace>/astraforge-llm-proxy`

Replace `<namespace>` with your GitHub username or org (lowercase) and keep the PAT scope to `read:packages` when pulling from Portainer.

## Portainer prerequisites

1. Create a GitHub PAT with `read:packages`.
2. In Portainer, go to *Registries* → *Add registry*, choose *GitHub Container Registry* with `ghcr.io` and supply your GitHub username + PAT.

## GitHub Actions setup (GHCR publishing)

1. In GitHub: *Settings → Actions → General → Workflow permissions* → choose **Read and write permissions** so `GITHUB_TOKEN` can push to GHCR.
2. If the org enforces package publishing restrictions, allow the repo to publish to GHCR (`ghcr.io/<owner>/astraforge-*`).
3. Ensure Actions are enabled for the repo/organization.
4. The CI workflow lives at `.github/workflows/ci.yaml`. Pushes to `main` (and tags/branches) build and push images; pull requests build only (no push).

## Stack template (isolated network + nginx reverse proxy)

Use this Portainer stack to keep everything on a private overlay network and expose only nginx (listening on host port `8081`). Swap `<namespace>`, set hostnames, and adjust environment values for your TrueNAS secrets:

```yaml
version: "3.9"
services:
  reverse-proxy:
    image: nginx:1.27
    ports:
      - "8081:8081"
    networks:
      - astraforge
    configs:
      - source: nginx_conf
        target: /etc/nginx/conf.d/default.conf

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: astraforge
      POSTGRES_USER: astraforge
      POSTGRES_PASSWORD: astraforge
    volumes:
      - postgres-data:/var/lib/postgresql/data
    command: ["postgres", "-p", "5433"]
    networks:
      - astraforge

  redis:
    image: redis:7
    networks:
      - astraforge

  llm-proxy:
    image: ghcr.io/<namespace>/astraforge-llm-proxy:latest
    environment:
      OPENAI_API_KEY: ${OPENAI_API_KEY:?set OPENAI_API_KEY}
      LLM_MODEL: ${LLM_MODEL:-gpt-4o-mini}
    networks:
      - astraforge

  backend-migrate:
    image: ghcr.io/<namespace>/astraforge-backend:latest
    command: python manage.py migrate
    environment:
      DATABASE_URL: postgres://astraforge:astraforge@postgres:5433/astraforge
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - postgres
      - redis
    networks:
      - astraforge

  backend:
    image: ghcr.io/<namespace>/astraforge-backend:latest
    command: python manage.py runserver 0.0.0.0:8001
    environment:
      DATABASE_URL: postgres://astraforge:astraforge@postgres:5433/astraforge
      REDIS_URL: redis://redis:6379/0
      EXECUTOR: codex
      RUN_LOG_STREAMER: redis
      CELERY_TASK_ALWAYS_EAGER: "0"
      ASTRAFORGE_EXECUTE_COMMANDS: "1"
      LOG_LEVEL: INFO
    depends_on:
      - postgres
      - redis
      - backend-migrate
      - llm-proxy
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    networks:
      - astraforge

  backend-worker:
    image: ghcr.io/<namespace>/astraforge-backend:latest
    command: celery -A astraforge.config.celery_app worker --loglevel=info -Q astraforge.core,astraforge.default --beat
    environment:
      DATABASE_URL: postgres://astraforge:astraforge@postgres:5433/astraforge
      REDIS_URL: redis://redis:6379/0
      EXECUTOR: codex
      RUN_LOG_STREAMER: redis
      CELERY_TASK_ALWAYS_EAGER: "0"
      ASTRAFORGE_EXECUTE_COMMANDS: "1"
      LOG_LEVEL: INFO
    depends_on:
      - postgres
      - redis
      - backend-migrate
      - llm-proxy
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    networks:
      - astraforge

  frontend:
    image: ghcr.io/<namespace>/astraforge-frontend:latest
    command: pnpm dev --host 0.0.0.0 --port 5174
    environment:
      VITE_API_URL: http://backend:8001
    depends_on:
      - backend
    networks:
      - astraforge

volumes:
  postgres-data:

networks:
  astraforge:

configs:
  nginx_conf:
    content: |
      map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
      }

      upstream frontend_app {
        server frontend:5174;
      }

      upstream backend_api {
        server backend:8001;
      }

      server {
        listen 8081;
        server_name astraforge.example.com api.astraforge.example.com;

        location / {
          proxy_pass http://frontend_app;
          proxy_set_header Host $host;
          proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
          proxy_http_version 1.1;
          proxy_set_header Upgrade $http_upgrade;
          proxy_set_header Connection $connection_upgrade;
        }

        location /api/ {
          proxy_pass http://backend_api;
          proxy_set_header Host $host;
          proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
          proxy_http_version 1.1;
          proxy_set_header Upgrade $http_upgrade;
          proxy_set_header Connection $connection_upgrade;
        }

        # WebSockets (adjust path to your websocket endpoint)
        location /ws/ {
          proxy_pass http://backend_api;
          proxy_set_header Host $host;
          proxy_http_version 1.1;
          proxy_set_header Upgrade $http_upgrade;
          proxy_set_header Connection $connection_upgrade;
        }
      }
```

### Deployment flow

1. Push to `main` to publish fresh `latest`/branch/SHA tags to GHCR.
2. In Portainer, create a new stack, paste the YAML above, and set env vars (`OPENAI_API_KEY`, optional `LLM_MODEL`, and any Django settings you override).
3. Deploy; Portainer will pull GHCR images, run migrations, and bring up the API, worker, LLM proxy, and frontend.
4. Update by re-deploying the stack with a new tag (e.g., a specific SHA) or letting it track `latest`.

Notes:
- Keep `/var/run/docker.sock` mounted for the backend/worker only if you rely on Docker-based workspace execution; remove it on clusters where that access is not allowed.
- Swap Postgres/Redis for external services if your TrueNAS already hosts them; update the URLs accordingly.
- Set DNS for `astraforge.example.com` and `api.astraforge.example.com` (or your preferred hostnames) to the TrueNAS/Portainer host so nginx can route traffic. Add TLS by mounting certs/keys and updating the nginx config with `listen 443 ssl` plus `ssl_certificate` / `ssl_certificate_key`.
