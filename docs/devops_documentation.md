# DevOps-документация проекта InfraDrive

## 1. Описание Ansible-ролей и IaC-практик

Все задачи используют полные квалифицированные имена модулей (**FQCN**: `ansible.builtin.*`, `community.docker.*`).

### 1.1. Роль `roles/docker`
* Проверяет целевую ОС (`Debian 13`) и архитектуру (`x86_64` / `aarch64`).
* Устанавливает `docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin`, `docker-compose-plugin` из официального репозитория Docker для Debian `trixie`.
* Генерирует `/etc/docker/daemon.json` через `to_nice_json` с валидацией синтаксиса JSON (`python3 -m json.tool`), перезапускает службу только при изменениях и проверяет статус `docker.service`.

### 1.2. Роль `roles/valkey_meta`
* Проверяет наличие общей сети `infradrive_net`.
* Создаёт каталог `/etc/infradrive/valkey` с правами `0700` и конфигурационный файл `valkey.conf` с правами `0640` (`root:1000`), исключая чтение пароля непривилегированными пользователями хоста.
* Монтирует persistent volume `infradrive_valkey_data` в `/data`, настраивает AOF + RDB, перезапускает контейнер через handler при изменении конфигурации и проверяет ответ `PONG`.

### 1.3. Роль `roles/storage`
* Валидирует уникальность имён и томов трёх равноправных нод (`storage-1`, `storage-2`, `storage-3`), а также корректность лимитов памяти и CPU.
* Явно разделяет промышленный режим (`storage_mode: "service"`, по умолчанию) и режим инфраструктурных заглушек (`storage_mode: "stub"`). В режиме `service` блокирует запуск без реального образа storage-демона.
* Маркирует контейнеры меткой `infradrive.storage.mode` (`service` или `stub`) и проверяет доступность `/data` на запись.

### 1.4. Роль `roles/fastapi`
* Блокирует запуск при пустом `fastapi_image`, отсутствии локального образа (при `fastapi_pull_image: false`), а также запрещает использование образов-заглушек (`debian`, `alpine`, `sleep`) при `fastapi_allow_mock: false`.
* Подключает контейнер к `infradrive_net`, не публикует порты наружу по умолчанию (`fastapi_publish_port: false`) и проверяет переход контейнера в состояние `Running`.

## 2. Тестирование через Molecule

* Сценарии всех четырёх ролей запускаются в контейнерах `geerlingguy/docker-debian13-ansible:latest` с `systemd` (`/sbin/init`).
* Для работы вложенного Docker (`valkey_meta`, `storage`, `fastapi`) без ошибки ядра `overlayfs on top of overlayfs` каталоги `/var/lib/docker` и `/var/lib/containerd` монтируются в именованные Docker-тома.
* Что проверяют тесты `verify.yml`:
  * `docker`: статус `docker.service`, работа `docker version`, `docker compose version`, `docker info`.
  * `valkey_meta`: права `0640` на `valkey.conf`, ответ `PONG`, сохранение ключа при удалении и пересоздании контейнера, отклонение неавторизованных запросов (`NOAUTH`) при включённом `valkey_password` и чтение данных с авторизацией.
  * `storage`: создание трёх томов, запуск `storage-1..3` в явном режиме `stub`, изоляция данных `/data` между нодами и срабатывание fail-fast блокировки в режиме `service` при пустом `storage_image`.
  * `fastapi`: работа инфраструктурного mock-контейнера (`fastapi_allow_mock: true`), закрытость внешних портов, блокировка пустого `fastapi_image` и блокировка образа-заглушки при `fastapi_allow_mock: false`.

## 3. Безопасность
* Пароли и секреты не хранятся в Git и передаются через переменные окружения (`INFRADRIVE_VALKEY_PASSWORD`, `fastapi_env`) с защитой задач директивой `no_log`.
* Внутренние порты Valkey, Storage и FastAPI по умолчанию не публикуются на хост.
* Данная инфраструктура является учебной и не гарантирует соответствия требованиям 152-ФЗ или GDPR без проведения отдельного организационно-технического аудита.

## 4. Блокеры и вопросы для согласования с Backend-разработчиком
1. **Код и Docker-образ Storage-сервиса (`INFRADRIVE_STORAGE_IMAGE`):** протокол приёма/отдачи chunks, порт и команда запуска.
2. **Docker-образ FastAPI Backend (`INFRADRIVE_FASTAPI_IMAGE`, `INFRADRIVE_FASTAPI_TAG`):** имя и тег собранного образа.
3. **Схема переменных окружения Backend (`fastapi_env`):** имена переменных для подключения к `infradrive-valkey:6379` и `storage-1..3`.
4. **HTTP API контракты (`fastapi_healthcheck_test`, `BACKEND_UPLOAD_URL`, `BACKEND_DOWNLOAD_URL_TEMPLATE`):** точные URI для включения healthcheck и разблокировки сквозного теста отказоустойчивости RF=2 в `test_failover.sh`.
