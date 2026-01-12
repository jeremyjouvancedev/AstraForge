# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    WORKSPACE_DIR=/workspace \
    PIP_CACHE_DIR=/workspace/.cache/pip \
    PATH=/workspace/.local/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git tini \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libxkbcommon0 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash sandbox \
    && mkdir -p "${WORKSPACE_DIR}" \
    && mkdir -p "${WORKSPACE_DIR}"/.cache/pip \
    && mkdir -p "${WORKSPACE_DIR}"/.local \
    && chown -R sandbox:sandbox "${WORKSPACE_DIR}"

RUN pip install --no-cache-dir playwright \
    && playwright install-deps chromium

USER sandbox
RUN playwright install chromium

WORKDIR /workspace

COPY --chown=sandbox:sandbox entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8000

CMD ["tini", "--", "/usr/local/bin/entrypoint.sh"]
