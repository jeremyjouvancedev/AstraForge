FROM node:20-alpine AS frontend-build

WORKDIR /frontend

ENV PNPM_HOME="/pnpm"
ENV PATH="${PNPM_HOME}:${PATH}"

# Use pnpm 9 to match the lockfile format.
RUN corepack enable && corepack prepare pnpm@9.12.2 --activate

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm run build

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates openssh-client curl tar \
    && ARCH=$(uname -m) \
    && curl -fsSL https://download.docker.com/linux/static/stable/${ARCH}/docker-25.0.5.tgz | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
    && case "${ARCH}" in \
        x86_64) KUBECTL_ARCH=amd64 ;; \
        aarch64) KUBECTL_ARCH=arm64 ;; \
        *) echo "Unsupported architecture ${ARCH}" && exit 1 ;; \
    esac \
    && curl -fsSLo /usr/local/bin/kubectl "https://dl.k8s.io/release/v1.30.3/bin/linux/${KUBECTL_ARCH}/kubectl" \
    && chmod +x /usr/local/bin/kubectl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements-dev.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/ /app/
COPY --from=frontend-build /frontend/dist /app/frontend_dist

RUN python manage.py collectstatic --noinput

EXPOSE 8001

CMD ["gunicorn", "astraforge.config.wsgi:application", "--bind", "0.0.0.0:8001"]
