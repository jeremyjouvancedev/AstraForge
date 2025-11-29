# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    WORKSPACE_DIR=/workspace \
    DISPLAY=:99

# GUI base (headless X server + lightweight WM) and useful CLI tools.
# Includes ImageMagick + x11-apps so the backend can capture screenshots via Xvfb.
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb x11vnc fluxbox imagemagick x11-apps curl ca-certificates git tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for the sandbox
RUN useradd -ms /bin/bash sandbox \
    && mkdir -p "${WORKSPACE_DIR}" \
    && chown sandbox:sandbox "${WORKSPACE_DIR}"

USER sandbox
WORKDIR /workspace

EXPOSE 8000

# Start Xvfb and Fluxbox; replace tail with sandbox daemon entrypoint when available.
CMD ["tini", "--", "sh", "-c", "Xvfb :99 -screen 0 1280x720x24 & fluxbox >/tmp/fluxbox.log 2>&1 & tail -f /dev/null"]
