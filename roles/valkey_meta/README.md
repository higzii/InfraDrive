# Роль `valkey_meta`

Развёртывает контейнер Valkey для хранения метаданных файлов, сведений о chunks, расположении реплик и runtime-состояния проекта InfraDrive.

## Требования
* ОС целевого хоста: Debian 13 (`trixie`).
* Установленный Docker CE (роль `docker`) и пакет `python3-docker`.
* Предварительно созданная Docker-сеть (`infradrive_net`).

## Основные переменные (`defaults/main.yml`)
* `valkey_container_name`: `"infradrive-valkey"`
* `valkey_image`: `"valkey/valkey"`
* `valkey_image_tag`: `"8.0-alpine"`
* `valkey_volume_name`: `"infradrive_valkey_data"`
* `valkey_network_name`: `"infradrive_net"`
* `valkey_port`: `6379`
* `valkey_publish_ports`: `false` (доступ только внутри Docker-сети по умолчанию)
* `valkey_password`: читается из переменной окружения `INFRADRIVE_VALKEY_PASSWORD`
