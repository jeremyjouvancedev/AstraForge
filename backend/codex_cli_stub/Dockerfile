ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    NPM_CONFIG_CACHE=/workspace/.cache/npm \
    PIP_CACHE_DIR=/workspace/.cache/pip \
    PNPM_HOME=/workspace/.cache/pnpm \
    NODE_TLS_REJECT_UNAUTHORIZED=0

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates tini nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Copy .npmrc for custom npm registry configuration (e.g., private registries)
COPY .npmrc* /root/

RUN npm install -g @openai/codex \
    && if [ -f /usr/local/bin/codex ]; then mv /usr/local/bin/codex /usr/local/bin/codex-real; fi

RUN useradd -m -u 1000 appuser \
    && mkdir -p /workspace/.cache/npm /workspace/.cache/pip /workspace/.cache/pnpm \
    && chown -R appuser:appuser /workspace

WORKDIR /workspace

COPY bin/codex /usr/local/bin/codex
COPY bin/codex-proxy /usr/local/bin/codex-proxy

RUN chmod +x /usr/local/bin/codex \
    && chmod +x /usr/local/bin/codex-proxy

USER appuser

CMD ["sleep", "infinity"]
