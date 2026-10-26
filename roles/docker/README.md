# Роль `docker`

Устанавливает и настраивает Docker CE и Docker Compose на целевом хосте под управлением Debian 13 (`trixie`).

## Задачи роли
* Проверка соответствия ОС (`Debian 13`).
* Подключение официального APT-репозитория Docker с GPG-ключом.
* Установка пакетов `docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin`, `docker-compose-plugin`.
* Конфигурация `/etc/docker/daemon.json` (ротация логов `json-file` до 3 файлов по 10 МБ).
* Обеспечение автозапуска и работы службы `docker.service`.
