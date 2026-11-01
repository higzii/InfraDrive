#!/usr/bin/env bash
set -euo pipefail

# Run this script INSIDE infradrive-target so Docker commands address the nested daemon.

STORAGE_NODES=("storage-1" "storage-2" "storage-3")
TARGET_STOP_NODE="${TARGET_STOP_NODE:-}"
BACKEND_UPLOAD_URL="${BACKEND_UPLOAD_URL:-http://127.0.0.1:8000/files}"
BACKEND_DOWNLOAD_URL_TEMPLATE="${BACKEND_DOWNLOAD_URL_TEMPLATE:-http://127.0.0.1:8000/files/{file_id}}"
BACKEND_API_TOKEN="${INFRADRIVE_API_TOKEN:-}"

TMP_DIR=""
NODE_WAS_STOPPED=0

log_info() { printf '[INFO] %s\n' "$1"; }
log_warn() { printf '[WARN] %s\n' "$1" >&2; }
log_error() { printf '[ERROR] %s\n' "$1" >&2; }

cleanup() {
  if [[ "${NODE_WAS_STOPPED}" -eq 1 && -n "${TARGET_STOP_NODE}" ]]; then
    log_info "Restoring stopped container '${TARGET_STOP_NODE}'..."
    docker start "${TARGET_STOP_NODE}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then rm -rf "${TMP_DIR}"; fi
}
trap cleanup INT TERM EXIT

for cmd in docker sha256sum dd curl python3; do
  command -v "${cmd}" >/dev/null 2>&1 || { log_error "Missing required command '${cmd}'."; exit 1; }
done
docker info >/dev/null 2>&1 || { log_error "Docker daemon is unavailable."; exit 1; }

log_info "Checking storage nodes and persistent volumes..."
for node in "${STORAGE_NODES[@]}"; do
  [[ "$(docker inspect -f '{{.State.Running}}' "${node}" 2>/dev/null || echo false)" == "true" ]] \
    || { log_error "Storage node '${node}' is not running."; exit 1; }
  mode="$(docker inspect -f '{{index .Config.Labels "infradrive.storage.mode"}}' "${node}" 2>/dev/null || echo unknown)"
  [[ "${mode}" == "service" ]] || { log_error "${node} is not running a real storage service (mode=${mode})."; exit 2; }
  docker exec "${node}" sh -c 'test -d /data && test -w /data' \
    || { log_error "/data is not writable on ${node}."; exit 1; }
done

TMP_DIR="$(mktemp -d)"
source_file="${TMP_DIR}/payload.bin"
download_file="${TMP_DIR}/downloaded.bin"
# Keep the payload below the default 4 MiB chunk size so it has one replica pair.
dd if=/dev/urandom of="${source_file}" bs=1024 count=256 status=none
source_sha="$(sha256sum "${source_file}" | awk '{print $1}')"

log_info "Uploading a 256 KiB test file..."
headers=()
if [[ -n "${BACKEND_API_TOKEN}" ]]; then headers=(-H "Authorization: Bearer ${BACKEND_API_TOKEN}"); fi
upload_json="$(curl -fsS "${headers[@]}" -F "file=@${source_file}" "${BACKEND_UPLOAD_URL}")"
file_id="$(printf '%s' "${upload_json}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["file_id"])')"
replica_json="$(printf '%s' "${upload_json}" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["chunk_replicas"][0]["replicas"]))')"

if [[ -z "${TARGET_STOP_NODE}" ]]; then
  TARGET_STOP_NODE="$(printf '%s' "${replica_json}" | python3 -c 'import json,sys; print(json.load(sys.stdin)[0])')"
fi

contains_replica="$(printf '%s' "${replica_json}" | python3 -c 'import json,sys; print("yes" if sys.argv[1] in json.load(sys.stdin) else "no")' "${TARGET_STOP_NODE}")"
if [[ "${contains_replica}" != "yes" ]]; then
  log_error "TARGET_STOP_NODE='${TARGET_STOP_NODE}' is not one of the uploaded chunk replicas: ${replica_json}"
  exit 1
fi

log_info "Upload complete. file_id=${file_id}; stopping replica ${TARGET_STOP_NODE}..."
NODE_WAS_STOPPED=1
docker stop "${TARGET_STOP_NODE}" >/dev/null

placeholder='{file_id}'
download_url="${BACKEND_DOWNLOAD_URL_TEMPLATE//"$placeholder"/${file_id}}"
log_info "Downloading through the remaining replica..."
curl -fsS "${headers[@]}" "${download_url}" -o "${download_file}"
download_sha="$(sha256sum "${download_file}" | awk '{print $1}')"

[[ "${source_sha}" == "${download_sha}" ]] || {
  log_error "SHA-256 mismatch: expected ${source_sha}, got ${download_sha}."
  exit 1
}
log_info "PASS: download succeeded with one replica stopped; SHA-256 matches."
