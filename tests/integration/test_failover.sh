#!/usr/bin/env bash
set -euo pipefail

STORAGE_NODES=("storage-1" "storage-2" "storage-3")
TARGET_STOP_NODE="${TARGET_STOP_NODE:-storage-2}"

BACKEND_UPLOAD_URL="${BACKEND_UPLOAD_URL:-}"
BACKEND_DOWNLOAD_URL_TEMPLATE="${BACKEND_DOWNLOAD_URL_TEMPLATE:-}"

TMP_DIR=""
NODE_WAS_STOPPED=0

log_info() {
  printf '[INFO] %s\n' "$1"
}

log_warn() {
  printf '[WARN] %s\n' "$1" >&2
}

log_error() {
  printf '[ERROR] %s\n' "$1" >&2
}

cleanup() {
  if [[ "${NODE_WAS_STOPPED}" -eq 1 ]]; then
    log_info "Восстановление остановленного контейнера '${TARGET_STOP_NODE}'..."
    docker start "${TARGET_STOP_NODE}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]]; then
    rm -rf "${TMP_DIR}"
  fi
}
trap cleanup INT TERM EXIT

check_prerequisites() {
  for cmd in docker sha256sum dd; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
      log_error "Не найдена обязательная утилита '${cmd}'."
      exit 1
    fi
  done
  if ! docker info >/dev/null 2>&1; then
    log_error "Демон Docker недоступен."
    exit 1
  fi
}

verify_infrastructure_volume_persistence() {
  log_info "Этап 1: Проверка инфраструктурной сохранности volume при остановке '${TARGET_STOP_NODE}'..."
  for node in "${STORAGE_NODES[@]}"; do
    local running
    running="$(docker inspect -f '{{.State.Running}}' "${node}" 2>/dev/null || echo "false")"
    if [[ "${running}" != "true" ]]; then
      log_error "Storage-нода '${node}' должна быть запущена перед началом теста."
      exit 1
    fi
  done

  local marker_file="/data/.infra_persistence_probe_$$"
  local expected_token
  expected_token="probe_$(date +%s)_$$"

  docker exec "${TARGET_STOP_NODE}" sh -c "printf '%s' '${expected_token}' > ${marker_file} && sync"
  NODE_WAS_STOPPED=1
  docker stop "${TARGET_STOP_NODE}" >/dev/null

  for peer in "${STORAGE_NODES[@]}"; do
    if [[ "${peer}" != "${TARGET_STOP_NODE}" ]]; then
      local peer_running
      peer_running="$(docker inspect -f '{{.State.Running}}' "${peer}")"
      if [[ "${peer_running}" != "true" ]]; then
        log_error "Остановка '${TARGET_STOP_NODE}' нарушила работу ноды '${peer}'."
        exit 1
      fi
    fi
  done

  docker start "${TARGET_STOP_NODE}" >/dev/null
  NODE_WAS_STOPPED=0

  local actual_token
  actual_token="$(docker exec "${TARGET_STOP_NODE}" cat "${marker_file}")"
  docker exec "${TARGET_STOP_NODE}" rm -f "${marker_file}"

  if [[ "${actual_token}" != "${expected_token}" ]]; then
    log_error "Данные в persistent volume ноды '${TARGET_STOP_NODE}' потеряны после перезапуска контейнера."
    exit 1
  fi

  log_info "Этап 1 пройден: контейнер '${TARGET_STOP_NODE}' корректно перезапускается, том /data сохраняет данные."
  log_warn "ВНИМАНИЕ: Остановка контейнера подтверждает только работу Docker volume, но НЕ доказывает репликацию RF=2 через backend."
}

verify_application_rf2_failover() {
  log_info "Этап 2: Сквозная проверка отказоустойчивости RF=2 через Backend API..."
  for node in "${STORAGE_NODES[@]}"; do
    local node_mode
    node_mode="$(docker inspect -f '{{index .Config.Labels "infradrive.storage.mode"}}' "${node}" 2>/dev/null || echo "unknown")"
    if [[ "${node_mode}" == "stub" ]]; then
      log_error "Нода '${node}' запущена в режиме инфраструктурной заглушки (mode=stub) без storage-демона."
      log_error "Сквозная проверка RF=2 невозможна на контейнерах-заглушках."
      exit 2
    fi
  done

  if [[ -z "${BACKEND_UPLOAD_URL}" || -z "${BACKEND_DOWNLOAD_URL_TEMPLATE}" ]]; then
    log_error "Сквозной тест RF=2 заблокирован: не заданы BACKEND_UPLOAD_URL и BACKEND_DOWNLOAD_URL_TEMPLATE."
    log_error "В репозитории отсутствует код backend и спецификация HTTP API загрузки/скачивания файлов."
    log_error "После согласования API укажите BACKEND_UPLOAD_URL и BACKEND_DOWNLOAD_URL_TEMPLATE для проверки:"
    log_error "  1) Загрузка файла через backend API и расчёт SHA-256;"
    log_error "  2) Остановка одной из storage-нод с репликой;"
    log_error "  3) Скачивание файла из оставшейся реплики через backend API и сверка SHA-256."
    exit 2
  fi

  if ! command -v curl >/dev/null 2>&1; then
    log_error "Для выполнения HTTP-запросов к backend требуется утилита 'curl'."
    exit 1
  fi

  TMP_DIR="$(mktemp -d)"
  local src_file="${TMP_DIR}/test_payload.bin"
  local dst_file="${TMP_DIR}/downloaded_payload.bin"

  dd if=/dev/urandom of="${src_file}" bs=1024 count=256 status=none
  local src_sha256
  src_sha256="$(sha256sum "${src_file}" | awk '{print $1}')"

  log_info "Загрузка тестового файла (SHA-256: ${src_sha256}) в backend..."
  local file_id
  file_id="$(curl -fsS -F "file=@${src_file}" "${BACKEND_UPLOAD_URL}")"
  if [[ -z "${file_id}" ]]; then
    log_error "Backend не вернул идентификатор загруженного файла."
    exit 1
  fi

  log_info "Остановка ноды '${TARGET_STOP_NODE}' для проверки чтения из второй реплики (RF=2)..."
  NODE_WAS_STOPPED=1
  docker stop "${TARGET_STOP_NODE}" >/dev/null

  local download_url="${BACKEND_DOWNLOAD_URL_TEMPLATE//\{file_id\}/${file_id}}"
  log_info "Скачивание файла при остановленной ноде '${TARGET_STOP_NODE}'..."
  curl -fsS "${download_url}" -o "${dst_file}"

  local dst_sha256
  dst_sha256="$(sha256sum "${dst_file}" | awk '{print $1}')"

  if [[ "${src_sha256}" != "${dst_sha256}" ]]; then
    log_error "Несовпадение SHA-256 после отказа ноды! Ожидалось: ${src_sha256}, получено: ${dst_sha256}."
    exit 1
  fi

  log_info "Этап 2 пройден: файл успешно скачан из оставшейся реплики, контрольная сумма SHA-256 совпала."
}

main() {
  check_prerequisites
  verify_infrastructure_volume_persistence
  verify_application_rf2_failover
}

main "$@"
