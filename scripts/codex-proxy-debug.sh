#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${1:-}"

if [[ -z "${CONTAINER_NAME}" ]]; then
  if command -v rg >/dev/null 2>&1; then
    CONTAINER_NAME="$(docker ps --format '{{.Names}}' | rg '^codex-' | head -n 1 || true)"
  else
    CONTAINER_NAME="$(docker ps --format '{{.Names}}' | grep -E '^codex-' | head -n 1 || true)"
  fi
fi

if [[ -z "${CONTAINER_NAME}" ]]; then
  echo "No codex-* container found. Pass the container name as arg 1."
  exit 1
fi

echo "==> Using container: ${CONTAINER_NAME}"

echo
echo "==> Attached networks"
docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{println $k}}{{end}}' "${CONTAINER_NAME}" || true
docker inspect -f 'NetworkMode: {{.HostConfig.NetworkMode}}' "${CONTAINER_NAME}" || true

echo
echo "==> DNS + health check to llm-proxy"
docker exec -it "${CONTAINER_NAME}" sh -lc '
  getent hosts llm-proxy || true
  if command -v curl >/dev/null 2>&1; then
    curl -sv http://llm-proxy:8080/healthz || true
  elif command -v python3 >/dev/null 2>&1; then
    python3 - <<'"'"'PY'"'"'
import sys
import urllib.request
try:
    with urllib.request.urlopen("http://llm-proxy:8080/healthz", timeout=5) as resp:
        print("HTTP", resp.status)
        print(resp.read().decode("utf-8", "replace"))
except Exception as exc:
    print("healthz failed:", exc, file=sys.stderr)
PY
  else
    echo "Neither curl nor python3 is available in the container."
  fi
'

echo
echo "==> Relevant env vars inside container"
docker exec -it "${CONTAINER_NAME}" sh -lc 'if command -v rg >/dev/null 2>&1; then env | rg -i "proxy|ollama|openai|llm"; else env | grep -Ei "proxy|ollama|openai|llm"; fi || true'

echo
echo "==> Codex config.toml inside container"
docker exec -it "${CONTAINER_NAME}" sh -lc '
  if [ -f /workspace/.codex/config.toml ]; then
    cat /workspace/.codex/config.toml
  else
    cat ~/.codex/config.toml || true
  fi
'
