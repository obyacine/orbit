#!/usr/bin/env bash
# Runs on the server, in /opt/orbit, called by the deploy job of GitHub Actions:
#   ./deploy.sh <image tag>
# Pulls the images, starts the stack, prepares the admin / workspace / agent key, then checks health.
set -euo pipefail
cd "$(dirname "$0")"

export ORBIT_IMAGE_TAG="${1:-latest}"
compose=(docker compose -f compose.yml)

echo "==> Orbit ${ORBIT_IMAGE_TAG}: pulling images"
"${compose[@]}" pull --quiet

echo "==> Starting the stack"
"${compose[@]}" up -d --remove-orphans
# Remembered so that a configuration change applied by Ansible restarts this exact build.
echo "${ORBIT_IMAGE_TAG}" > IMAGE_TAG

echo "==> Waiting for the API"
api_port="$(grep -E '^ORBIT_API_PORT=' .env | cut -d= -f2)"
for _ in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:${api_port:-3213}/api/instances/" >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS "http://127.0.0.1:${api_port:-3213}/api/instances/" >/dev/null

echo "==> Preparing the admin, the workspace and the agent's API key"
set -a
# shellcheck disable=SC1091
. ./.env
# shellcheck disable=SC1091
. ./bootstrap.env
set +a
"${compose[@]}" exec -T \
  -e ORBIT_ADMIN_EMAIL -e ORBIT_ADMIN_PASSWORD -e ORBIT_ADMIN_NAME \
  -e ORBIT_WORKSPACE_SLUG -e ORBIT_WORKSPACE_NAME -e ORBIT_AGENT_API_KEY \
  api python manage.py orbit_bootstrap

echo "==> Checking the AI agent"
for _ in $(seq 1 30); do
  if "${compose[@]}" exec -T ai-service python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health')" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
"${compose[@]}" exec -T ai-service python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8001/health').read().decode())"

echo "==> Cleaning old images"
docker image prune -f >/dev/null

echo "==> Orbit ${ORBIT_IMAGE_TAG} is up"
"${compose[@]}" ps --format 'table {{.Service}}\t{{.Status}}'
