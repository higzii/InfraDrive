---

# InfraDrive: Развёртывание на macOS

Инструкция по развёртыванию учебного распределённого файлового хранилища с чанкованием по 4 МиБ и фактором репликации `RF=2`.

---

### Шаг 1. Предварительные требования

1. Запустите **Docker Desktop** (или OrbStack). Проверьте статус демона:


```bash
docker info >/dev/null && echo "Docker готов!"

```


2. Установите Python и утилиты через Homebrew (если Homebrew не установлен: `/bin/bash -c "$(curl -fsSL [https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh](https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh))"`):


```bash
brew install python@3.11 git curl unzip

```



---

### Шаг 2. Распаковка архива и подготовка окружения

1. Распакуйте переданный ZIP-архив и перейдите в каталог проекта:
```bash
unzip InfraDrive.zip
cd InfraDrive

```


2. Сделайте исполняемыми скрипты тестирования и деплоя:


```bash
chmod +x deployment/*.sh tests/integration/*.sh

```


3. Соберите локальные Docker-образы нод хранения и бэкенда:


```bash
docker build -t infradrive/storage-daemon:0.1.0 ./storage-daemon
docker build -t infradrive/backend:0.1.0 ./backend

```


*Проверка:* `docker images | grep infradrive` должен вывести оба собранных образа.



---

### Вариант А: Режим разработки (Песочница с hot-reload)

Рекомендуемый режим для доработки интерфейса и бэкенда: инфраструктура запущена в Docker с проброшенными портами, а бэкенд крутится локально на хосте с автоматической перезагрузкой при сохранении кода (`--reload`).

1. **Запустите изолированную инфраструктуру в Docker:**
```bash
docker network create infradrive_net 2>/dev/null || true

# Запуск Valkey
docker run -d \
  --name infradrive-valkey \
  --hostname infradrive-valkey \
  --network infradrive_net \
  -p 127.0.0.1:6379:6379 \
  -v infradrive_valkey_data:/data \
  --restart unless-stopped \
  valkey/valkey:8.0-alpine \
  valkey-server --protected-mode no

# Запуск 3 узлов хранения
for i in 1 2 3; do
  docker run -d \
    --name "storage-$i" \
    --hostname "storage-$i" \
    --network infradrive_net \
    -p "127.0.0.1:800$i:8001" \
    -v "infradrive_storage_${i}_data:/data" \
    --restart unless-stopped \
    infradrive/storage-daemon:0.1.0
done

```


2. **Запустите бэкенд на хосте:**
```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e '.[test]'

export INFRADRIVE_VALKEY_HOST=127.0.0.1
export INFRADRIVE_STORAGE_NODES='storage-1=http://127.0.0.1:8001,storage-2=http://127.0.0.1:8002,storage-3=http://127.0.0.1:8003'

uvicorn infradrive.main:app --host 127.0.0.1 --port 8000 --reload

```


3. **Работа с сервисом:**
* Swagger UI доступен по адресу: `[http://127.0.0.1:8000](http://127.0.0.1:8000)` (авторедирект на `/docs`).


* Настроен `CORS` — веб-интерфейсы на любых локальных портах (`localhost:3000`, `localhost:5173`) могут свободно слать запросы к API.





---

### Вариант Б: Полное развёртывание стека в Docker через Ansible

Режим для проверки контейнеризованного деплоя (бэкенд также запускается внутри контейнера).

1. Подготовьте окружение Ansible:


```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
ansible-galaxy collection install -r requirements.yml

```


2. Запустите плейбук:


```bash
ansible-playbook playbooks/local-docker.yml \
  -e "ansible_python_interpreter=$(which python)" \
  -e "fastapi_publish_port=true" \
  -e "fastapi_host_port=8000" \
  -e "storage_image=infradrive/storage-daemon" \
  -e "storage_image_tag=0.1.0" \
  -e "fastapi_image=infradrive/backend" \
  -e "fastapi_image_tag=0.1.0" \
  -K

```


(Флаг `-K` запросит пароль `sudo` macOS для создания каталога `/etc/infradrive/valkey`).


3. Проверьте запущенные контейнеры:


```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

```


*Ожидается 5 контейнеров:* `infradrive-backend`, `storage-1`, `storage-2`, `storage-3`, `infradrive-valkey`.



---

### Шаг 3. Проверка работоспособности и тесты

1. Проверка эндпоинта здоровья:


```bash
curl -i http://127.0.0.1:8000/health

```


*Ожидаемый ответ:* HTTP `200 OK`:


```json
{"status":"ok","valkey":"ok","storage":{"storage-1":"ok","storage-2":"ok","storage-3":"ok"},"available_storage_nodes":3,"replication_factor":2}

```


2. Сквозной тест отказоустойчивости RF=2:


```bash
bash deployment/test_failover.sh

```


Скрипт загрузит файл 256 КиБ, остановит один из узлов с репликой и проверит скачивание со второго узла по контрольной сумме SHA-256.



---

### Шаг 4. Десктопный клиент (Tkinter GUI)

Для работы с файлами без браузера можно запустить десктопный клиент (использует только стандартную библиотеку Python):

```bash
python3 desktop-client/infradrive_gui.py

```

* В поле **Backend URL** укажите `[http://127.0.0.1:8000](http://127.0.0.1:8000)` и нажмите **Check**.


* Используйте кнопки **Upload file…** и **Download by ID…** для работы с файлами.



---

### Остановка и очистка

```bash
# Остановка всех контейнеров
docker rm -f infradrive-backend infradrive-valkey storage-1 storage-2 storage-3 2>/dev/null || true

# Полное удаление данных и сети (при необходимости)
docker network rm infradrive_net 2>/dev/null || true
docker volume rm infradrive_valkey_data infradrive_storage_1_data infradrive_storage_2_data infradrive_storage_3_data 2>/dev/null || true

```
