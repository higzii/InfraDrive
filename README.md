# InfraDrive — Инфраструктура (Ansible + Docker + Molecule)

Репозиторий содержит инфраструктурный код (IaC) на базе Ansible для развёртывания учебного распределённого файлового сервиса **InfraDrive** на целевом хосте под управлением **Debian 13 (trixie)**.

## 1. Архитектурный состав
* **Docker CE (`roles/docker`)**: установка и базовая конфигурация Docker CE и Docker Compose на Debian 13.
* **Общая сеть (`infradrive_net`)**: создаётся централизованно в `playbooks/site.yml` и объединяет все контейнеры по DNS-именам.
* **Valkey (`roles/valkey_meta`)**: контейнер `infradrive-valkey` с persistent volume `infradrive_valkey_data` для хранения метаданных файлов, сведений о chunks, расположении реплик и runtime-состояния.
* **Storage (`roles/storage`)**: три логически равноправные ноды (`storage-1`, `storage-2`, `storage-3`), каждая с отдельным persistent volume (`infradrive_storage_1_data..3`), смонтированным в `/data`.
* **FastAPI Backend (`roles/fastapi`)**: контейнер `infradrive-backend`, подключаемый к `infradrive_net`. Код и образ backend разрабатываются отдельно.

## 2. Требования (Prerequisites)

### Управляющий узел (Control Node — Arch Linux / Linux)
* Python 3.11+ и виртуальное окружение `venv`
* Запущенный сервис Docker (для Molecule)
* SSH-доступ к целевому хосту Debian 13 с правами `sudo` (или локальный Docker-контейнер с `ansible_connection: docker`)

### Целевой узел (Target Host)
* ОС **Debian 13 (`trixie`)** (проверяется через `ansible.builtin.assert`)
* Доступ к сети Интернет для загрузки пакетов APT и базовых Docker-образов

## 3. Установка зависимостей

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
ansible-galaxy collection install -r requirements.yml
chmod +x tests/integration/*.sh

```

## 4. Конфигурация и передача параметров

Секреты и параметры подключения не сохраняются в Git и передаются через переменные окружения:

| Переменная окружения | Назначение | Значение по умолчанию |
| --- | --- | --- |
| `INFRADRIVE_TARGET_HOST` | IP/DNS хоста или имя Docker-контейнера | `127.0.0.1` |
| `INFRADRIVE_TARGET_PORT` | SSH-порт целевого хоста | `22` |
| `INFRADRIVE_TARGET_USER` | Пользователь на целевом хосте | `debian` |
| `INFRADRIVE_ANSIBLE_CONNECTION` | Тип подключения (`ssh` или `docker`) | `ssh` |
| `INFRADRIVE_VALKEY_PASSWORD` | Пароль аутентификации Valkey (опционально) | `""` (без пароля) |
| `INFRADRIVE_FASTAPI_IMAGE` | Docker-образ backend (обязательно для роли `fastapi`) | `""` |
| `INFRADRIVE_FASTAPI_TAG` | Тег Docker-образа FastAPI backend | `latest` |

## 5. Команды запуска и тестирования

### Проверка синтаксиса

```bash
ansible-playbook playbooks/site.yml --syntax-check

```

### Запуск Molecule-тестов по ролям

```bash
cd roles/docker && molecule test && cd ../..
cd roles/valkey_meta && molecule test && cd ../..
cd roles/storage && molecule test && cd ../..
cd roles/fastapi && molecule test && cd ../..

```

### Развёртывание на целевом хосте

* Развёртывание базового инфраструктурного слоя (Docker, сеть, Valkey, 3 Storage-ноды):
```bash
ansible-playbook playbooks/site.yml --skip-tags fastapi

```


* Полный запуск со сквозным развёртыванием backend:
```bash
export INFRADRIVE_FASTAPI_IMAGE="infradrive/backend"
export INFRADRIVE_FASTAPI_TAG="0.1.0"
ansible-playbook playbooks/site.yml

```



### Запуск интеграционных проверок

```bash
bash tests/integration/test_health.sh
bash tests/integration/test_failover.sh

```


