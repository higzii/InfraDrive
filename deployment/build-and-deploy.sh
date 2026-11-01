#!/usr/bin/env bash
set -euo pipefail

# Run from the merged InfraDrive repository root, where playbooks/site.yml exists.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_CONTAINER="${INFRADRIVE_TARGET_CONTAINER:-infradrive-target}"
IMAGE_TAG="${INFRADRIVE_APP_TAG:-0.1.0}"
STORAGE_IMAGE="${INFRADRIVE_STORAGE_IMAGE:-infradrive/storage-daemon}"
BACKEND_IMAGE="${INFRADRIVE_FASTAPI_IMAGE:-infradrive/backend}"
FASTAPI_BIND_ADDRESS="${INFRADRIVE_FASTAPI_BIND_ADDRESS:-0.0.0.0}"

if [[ ! -f "${PROJECT_ROOT}/playbooks/site.yml" ]]; then
  echo "ERROR: playbooks/site.yml not found. Merge this app layer into the InfraDrive repository root first." >&2
  exit 1
fi

if ! docker inspect "${TARGET_CONTAINER}" >/dev/null 2>&1; then
  echo "ERROR: target container '${TARGET_CONTAINER}' does not exist." >&2
  exit 1
fi

if [[ "$(docker inspect -f '{{.State.Running}}' "${TARGET_CONTAINER}")" != "true" ]]; then
  echo "ERROR: target container '${TARGET_CONTAINER}' is not running." >&2
  exit 1
fi

echo "[1/4] Copying application sources into ${TARGET_CONTAINER}..."
docker exec "${TARGET_CONTAINER}" mkdir -p /opt/infradrive
docker cp "${PROJECT_ROOT}/storage-daemon" "${TARGET_CONTAINER}:/opt/infradrive/"
docker cp "${PROJECT_ROOT}/backend" "${TARGET_CONTAINER}:/opt/infradrive/"

echo "[2/4] Building storage image inside the target Docker daemon..."
docker exec "${TARGET_CONTAINER}" docker build \
  -t "${STORAGE_IMAGE}:${IMAGE_TAG}" \
  /opt/infradrive/storage-daemon

echo "[3/4] Building backend image inside the target Docker daemon..."
docker exec "${TARGET_CONTAINER}" docker build \
  -t "${BACKEND_IMAGE}:${IMAGE_TAG}" \
  /opt/infradrive/backend

echo "[4/4] Deploying real application containers with Ansible..."
export INFRADRIVE_STORAGE_MODE=service
export INFRADRIVE_STORAGE_IMAGE="${STORAGE_IMAGE}"
export INFRADRIVE_STORAGE_TAG="${IMAGE_TAG}"
export INFRADRIVE_FASTAPI_IMAGE="${BACKEND_IMAGE}"
export INFRADRIVE_FASTAPI_TAG="${IMAGE_TAG}"

# In the nested-Docker setup, bind inside the target container on all interfaces;
# the OUTER infradrive-target container must publish 127.0.0.1:8000 to the host.
ansible-playbook "${PROJECT_ROOT}/playbooks/site.yml" \
  -e fastapi_publish_port=true \
  -e "fastapi_bind_address=${FASTAPI_BIND_ADDRESS}" \
  -e fastapi_host_port=8000

echo
echo "InfraDrive backend should be reachable at http://127.0.0.1:8000/health"
echo "Run the desktop client on the machine that owns the published Docker host port."
