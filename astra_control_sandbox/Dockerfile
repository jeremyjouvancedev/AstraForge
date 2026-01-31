# syntax=docker/dockerfile:1
ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

# Company-specific customization arguments
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG NO_PROXY=""
ARG PIP_INDEX_URL=""
ARG PIP_TRUSTED_HOST=""
ARG EXTRA_CA_CERTS=""

ENV DEBIAN_FRONTEND=noninteractive \
    WORKSPACE_DIR=/workspace \
    PYTHONUSERBASE=/workspace/.local \
    PIP_USER=1 \
    PIP_CACHE_DIR=/workspace/.cache/pip \
    NPM_CONFIG_CACHE=/workspace/.cache/npm \
    PNPM_HOME=/workspace/.cache/pnpm \
    PATH=/workspace/.local/bin:$PATH \
    HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY}

USER root

# Install extra CA certificates if provided
RUN if [ -n "${EXTRA_CA_CERTS}" ]; then \
        echo "${EXTRA_CA_CERTS}" > /usr/local/share/ca-certificates/company-certs.crt \
        && update-ca-certificates; \
    fi

# Configure pip with persistent settings if custom registry is provided
RUN if [ -n "${PIP_INDEX_URL}" ]; then \
        mkdir -p /etc/pip && \
        echo "[global]" > /etc/pip/pip.conf && \
        echo "index-url = ${PIP_INDEX_URL}" >> /etc/pip/pip.conf && \
        if [ -n "${PIP_TRUSTED_HOST}" ]; then \
            echo "trusted-host = ${PIP_TRUSTED_HOST}" >> /etc/pip/pip.conf; \
        fi; \
    fi

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git tini \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libxkbcommon0 libgbm1 libasound2 \
    libreoffice poppler-utils \
    && curl -fsSLk https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash sandbox \
    && mkdir -p "${WORKSPACE_DIR}" \
    && mkdir -p "${WORKSPACE_DIR}"/.cache/pip "${WORKSPACE_DIR}"/.cache/npm "${WORKSPACE_DIR}"/.cache/pnpm \
    && mkdir -p "${WORKSPACE_DIR}"/.local

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 --timeout 300 \
        pandas python-docx openpyxl python-pptx pdfplumber \
    && pip install --retries 10 --timeout 300 \
        matplotlib Pillow reportlab \
    && pip install --retries 10 --timeout 300 \
        playwright \
    && playwright install-deps chromium \
    && chown -R sandbox:sandbox "${WORKSPACE_DIR}" \
    && chmod -R 777 "${WORKSPACE_DIR}"

USER sandbox
RUN NODE_TLS_REJECT_UNAUTHORIZED=0 playwright install chromium

WORKDIR /workspace

COPY --chown=sandbox:sandbox entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

CMD ["tini", "--", "/usr/local/bin/entrypoint.sh"]
