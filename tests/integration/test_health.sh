#!/usr/bin/env bash
set -euo pipefail

NETWORK_NAME="${INFRADRIVE_NETWORK_NAME:-infradrive_net}"
VALKEY_CONTAINER="${VALKEY_CONTAINER_NAME:-infradrive-valkey}"
VALKEY_VOLUME="${VALKEY_VOLUME_NAME:-infradrive_valkey_data}"
VALKEY_PORT="${VALKEY_PORT:-6379}"
VALKEY_PASSWORD="${INFRADRIVE_VALKEY_PASSWORD:-}"

STORAGE_NODES=("storage-1" "storage-2" "storage-3")
STORAGE_VOLUMES=("infradrive_storage_1_data" "infradrive_storage_2_data" "infradrive_storage_3_data")
STORAGE_SERVICE_REQUIRED="${STORAGE_SERVICE_REQUIRED:-false}"

FASTAPI_CONTAINER="${FASTAPI_CONTAINER_NAME:-infradrive-backend}"
FASTAPI_REQUIRED="${FASTAPI_REQUIRED:-false}"
BACKEND_HEALTH_URL="${BACKEND_HEALTH_URL:-}"

log_info() {
  printf '[INFO] %s\n' "$1"
}

log_warn() {
  printf '[WARN] %s\n' "$1" >&2
}

log_error() {
  printf '[ERROR] %s\n' "$1" >&2
}

check_prerequisites() {
  log_info "Проверка prerequisites..."
  if ! command -v docker >/dev/null 2>&1; then
    log_error "Команда 'docker' не найдена в PATH."
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    log_error "Демон Docker недоступен или у текущего пользователя нет прав доступа к Docker socket."
    exit 1
  fi
}

check_network() {
  log_info "Проверка общей Docker-сети '${NETWORK_NAME}'..."
  if ! docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
    log_error "Сеть '${NETWORK_NAME}' не существует."
    exit 1
  fi
}

check_valkey() {
  log_info "Проверка контейнера метаданных '${VALKEY_CONTAINER}' и volume '${VALKEY_VOLUME}'..."
  if ! docker volume inspect "${VALKEY_VOLUME}" >/dev/null 2>&1; then
    log_error "Docker volume '${VALKEY_VOLUME}' не найден."
    exit 1
  fi

  local running
  running="$(docker inspect -f '{{.State.Running}}' "${VALKEY_CONTAINER}" 2>/dev/null || echo "false")"
  if [[ "${running}" != "true" ]]; then
    log_error "Контейнер '${VALKEY_CONTAINER}' не запущен."
    exit 1
  fi

  local net_attached
  net_attached="$(docker inspect -f "{{index .NetworkSettings.Networks \"${NETWORK_NAME}\"}}" "${VALKEY_CONTAINER}")"
  if [[ -z "${net_attached}" || "${net_attached}" == "<no value>" ]]; then
    log_error "Контейнер '${VALKEY_CONTAINER}' не подключён к сети '${NETWORK_NAME}'."
    exit 1
  fi

  local ping_resp
  if [[ -n "${VALKEY_PASSWORD}" ]]; then
    ping_resp="$(docker exec -e REDISCLI_AUTH="${VALKEY_PASSWORD}" "${VALKEY_CONTAINER}" valkey-cli -p "${VALKEY_PORT}" ping 2>/dev/null | tr -d '\r')"
  else
    ping_resp="$(docker exec "${VALKEY_CONTAINER}" valkey-cli -p "${VALKEY_PORT}" ping 2>/dev/null | tr -d '\r')"
  fi

  if [[ "${ping_resp}" != "PONG" ]]; then
    log_error "Valkey не ответил PONG на команду ping (проверьте состояние сервиса и INFRADRIVE_VALKEY_PASSWORD)."
    exit 1
  fi
  log_info "Valkey доступен и отвечает PONG."
}

check_storage_nodes() {
  log_info "Проверка трёх равноправных storage-нод..."
  for idx in "${!STORAGE_NODES[@]}"; do
    local node="${STORAGE_NODES[$idx]}"
    local vol="${STORAGE_VOLUMES[$idx]}"

    if ! docker volume inspect "${vol}" >/dev/null 2>&1; then
      log_error "Persistent volume '${vol}' для ноды '${node}' не найден."
      exit 1
    fi

    local running
    running="$(docker inspect -f '{{.State.Running}}' "${node}" 2>/dev/null || echo "false")"
    if [[ "${running}" != "true" ]]; then
      log_error "Storage-нода '${node}' не запущена."
      exit 1
    fi

    local net_attached
    net_attached="$(docker inspect -f "{{index .NetworkSettings.Networks \"${NETWORK_NAME}\"}}" "${node}")"
    if [[ -z "${net_attached}" || "${net_attached}" == "<no value>" ]]; then
      log_error "Storage-нода '${node}' не подключена к сети '${NETWORK_NAME}'."
      exit 1
    fi

    local mounted_vol
    mounted_vol="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "${node}")"
    if [[ "${mounted_vol}" != "${vol}" ]]; then
      log_error "У ноды '${node}' в /data смонтирован '${mounted_vol}' вместо ожидаемого '${vol}'."
      exit 1
    fi

    if ! docker exec "${node}" sh -c 'test -d /data && test -w /data'; then
      log_error "Каталог /data внутри '${node}' недоступен для записи."
      exit 1
    fi

    local node_mode
    node_mode="$(docker inspect -f '{{index .Config.Labels "infradrive.storage.mode"}}' "${node}" 2>/dev/null || echo "unknown")"
    if [[ "${node_mode}" == "stub" ]]; then
      if [[ "${STORAGE_SERVICE_REQUIRED}" == "true" ]]; then
        log_error "Нода '${node}' работает в режиме инфраструктурной заглушки (stub), но STORAGE_SERVICE_REQUIRED=true."
        exit 1
      fi
      log_warn "Нода '${node}' запущена в инфраструктурном режиме заглушки (mode=stub): том '${vol}' (/data) и сеть исправны, прикладной storage-демон не развёрнут."
    else
      log_info "Нода '${node}' запущена (mode=${node_mode}), volume '${vol}' смонтирован в /data и доступен для записи."
    fi
  done
}

check_backend() {
  log_info "Проверка статуса контейнера backend '${FASTAPI_CONTAINER}'..."
  if docker inspect "${FASTAPI_CONTAINER}" >/dev/null 2>&1; then
    local running
    running="$(docker inspect -f '{{.State.Running}}' "${FASTAPI_CONTAINER}")"
    if [[ "${running}" != "true" ]]; then
      log_error "Контейнер '${FASTAPI_CONTAINER}' существует, но не запущен."
      exit 1
    fi
    log_info "Контейнер '${FASTAPI_CONTAINER}' запущен."

    if [[ -n "${BACKEND_HEALTH_URL}" ]]; then
      if ! command -v curl >/dev/null 2>&1; then
        log_error "Для проверки BACKEND_HEALTH_URL требуется утилита 'curl'."
        exit 1
      fi
      log_info "Проверка согласованного backend health endpoint..."
      curl -fsS "${BACKEND_HEALTH_URL}" >/dev/null
      log_info "Backend HTTP endpoint ответил успешно."
    else
      log_warn "BACKEND_HEALTH_URL не задан: HTTP API healthcheck пропущен до согласования endpoint с backend-разработчиком."
    fi
  else
    if [[ "${FASTAPI_REQUIRED}" == "true" ]]; then
      log_error "Контейнер '${FASTAPI_CONTAINER}' отсутствует (FASTAPI_REQUIRED=true)."
      exit 1
    fi
    log_warn "Контейнер '${FASTAPI_CONTAINER}' не развёрнут (FASTAPI_REQUIRED=false). Инфраструктурный слой Valkey + Storage исправен."
  fi
}

main() {
  check_prerequisites
  check_network
  check_valkey
  check_storage_nodes
  check_backend
  log_info "Инфраструктурная проверка здоровья стека InfraDrive успешно завершена."
}

main "$@"
