FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates tini nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @openai/codex

WORKDIR /workspace

COPY bin/codex-proxy /usr/local/bin/codex-proxy

RUN chmod +x /usr/local/bin/codex-proxy

CMD ["sleep", "infinity"]
