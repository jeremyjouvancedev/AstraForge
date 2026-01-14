# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    WORKSPACE_DIR=/workspace \
    PYTHONUSERBASE=/workspace/.local \
    PIP_USER=1 \
    PIP_CACHE_DIR=/workspace/.cache/pip \
    NPM_CONFIG_CACHE=/workspace/.cache/npm \
    PNPM_HOME=/workspace/.cache/pnpm \
    PATH=/workspace/.local/bin:$PATH

# GUI base (headless X server) and useful CLI tools.
# System dependencies for Playwright headless browsers.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates git tini \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libxkbcommon0 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for the sandbox
RUN useradd -ms /bin/bash sandbox \
    && mkdir -p "${WORKSPACE_DIR}" \
    && mkdir -p "${WORKSPACE_DIR}"/.cache/pip "${WORKSPACE_DIR}"/.cache/npm "${WORKSPACE_DIR}"/.cache/pnpm \
    && mkdir -p "${WORKSPACE_DIR}"/.local \
    && chown -R sandbox:sandbox "${WORKSPACE_DIR}"

# Install Playwright Python package globally and OS dependencies for Chromium.
RUN pip install --no-cache-dir playwright pandas python-docx openpyxl python-pptx pdfplumber matplotlib Pillow \
    && playwright install-deps chromium

# Switch to sandbox user and install Chromium browser binaries for that user.
USER sandbox
RUN playwright install chromium

WORKDIR /workspace

COPY --chown=sandbox:sandbox entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8000

# Start entrypoint
CMD ["tini", "--", "/usr/local/bin/entrypoint.sh"]
