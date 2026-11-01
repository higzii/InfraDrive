#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_CONTAINER="${INFRADRIVE_TARGET_CONTAINER:-infradrive-target}"

if ! docker inspect "${TARGET_CONTAINER}" >/dev/null 2>&1; then
  echo "ERROR: target container '${TARGET_CONTAINER}' does not exist." >&2
  exit 1
fi
if [[ "$(docker inspect -f '{{.State.Running}}' "${TARGET_CONTAINER}")" != "true" ]]; then
  echo "ERROR: target container '${TARGET_CONTAINER}' is not running." >&2
  exit 1
fi

# The inner Docker daemon is available only from within infradrive-target.
docker exec "${TARGET_CONTAINER}" mkdir -p /opt/infradrive/tests

docker cp "${PROJECT_ROOT}/deployment/test_failover.sh" \
  "${TARGET_CONTAINER}:/opt/infradrive/test_failover.sh"

if [[ -f "${PROJECT_ROOT}/tests/integration/test_health.sh" ]]; then
  docker cp "${PROJECT_ROOT}/tests/integration/test_health.sh" \
    "${TARGET_CONTAINER}:/opt/infradrive/test_health.sh"
  echo "[1/2] Running infrastructure/backend health test inside ${TARGET_CONTAINER}..."
  docker exec \
    -e FASTAPI_REQUIRED=true \
    -e STORAGE_SERVICE_REQUIRED=true \
    -e BACKEND_HEALTH_URL=http://127.0.0.1:8000/health \
    -e INFRADRIVE_VALKEY_PASSWORD="${INFRADRIVE_VALKEY_PASSWORD:-}" \
    "${TARGET_CONTAINER}" bash /opt/infradrive/test_health.sh
else
  echo "[INFO] tests/integration/test_health.sh not found; skipping health shell test."
fi

echo "[2/2] Running RF=2 storage failover test inside ${TARGET_CONTAINER}..."
docker exec \
  -e INFRADRIVE_API_TOKEN="${INFRADRIVE_API_TOKEN:-}" \
  -e TARGET_STOP_NODE="${TARGET_STOP_NODE:-}" \
  "${TARGET_CONTAINER}" bash /opt/infradrive/test_failover.sh
