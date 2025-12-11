FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    NPM_CONFIG_CACHE=/workspace/.cache/npm \
    PIP_CACHE_DIR=/workspace/.cache/pip \
    PNPM_HOME=/workspace/.cache/pnpm

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates tini nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @openai/codex \
    && if [ -f /usr/local/bin/codex ]; then mv /usr/local/bin/codex /usr/local/bin/codex-real; fi

RUN mkdir -p /workspace/.cache/npm /workspace/.cache/pip /workspace/.cache/pnpm

WORKDIR /workspace

COPY bin/codex /usr/local/bin/codex
COPY bin/codex-proxy /usr/local/bin/codex-proxy

RUN chmod +x /usr/local/bin/codex \
    && chmod +x /usr/local/bin/codex-proxy

CMD ["sleep", "infinity"]
