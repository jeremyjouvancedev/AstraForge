# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    WORKSPACE_DIR=/workspace \
    DISPLAY=:99 \
    PIP_CACHE_DIR=/workspace/.cache/pip \
    NPM_CONFIG_CACHE=/workspace/.cache/npm \
    PNPM_HOME=/workspace/.cache/pnpm

# GUI base (headless X server + lightweight WM) and useful CLI tools.
# Includes ImageMagick + x11-apps so the backend can capture screenshots via Xvfb,
# and system dependencies for Playwright headless browsers.
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb x11vnc fluxbox imagemagick x11-apps curl ca-certificates git tini \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libxkbcommon0 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for the sandbox
RUN useradd -ms /bin/bash sandbox \
    && mkdir -p "${WORKSPACE_DIR}" \
    && mkdir -p "${WORKSPACE_DIR}"/.cache/pip "${WORKSPACE_DIR}"/.cache/npm "${WORKSPACE_DIR}"/.cache/pnpm \
    && chown -R sandbox:sandbox "${WORKSPACE_DIR}"

# Install Playwright Python package globally and OS dependencies for Chromium.
RUN pip install --no-cache-dir playwright \
    && playwright install-deps chromium

# Switch to sandbox user and install Chromium browser binaries for that user.
USER sandbox
RUN playwright install chromium

WORKDIR /workspace

EXPOSE 8000

# Start Xvfb and Fluxbox; replace tail with sandbox daemon entrypoint when available.
CMD ["tini", "--", "sh", "-c", "Xvfb :99 -screen 0 1280x720x24 & fluxbox >/tmp/fluxbox.log 2>&1 & tail -f /dev/null"]
