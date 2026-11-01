# InfraDrive Storage Daemon

HTTP-демон хранит content-addressed chunks на persistent volume `/data`.

## Контракт

- `PUT /chunks/{sha256}` — потоково принимает бинарные данные, проверяет SHA-256 и атомарно заменяет файл.
- `GET /chunks/{sha256}` — возвращает бинарный chunk или `404`.
- `DELETE /chunks/{sha256}` — идемпотентно удаляет chunk (`204`).
- `GET /health` — проверяет доступность каталога данных.

`chunk_id` должен быть ровно 64 lowercase hex символа. Путь никогда не строится из произвольного имени файла. Максимальный размер настраивается `STORAGE_MAX_CHUNK_BYTES` (по умолчанию 4 MiB).

## Локальный запуск

```bash
cd storage-daemon
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
STORAGE_DATA_DIR=./data uvicorn storage_daemon.main:app --host 127.0.0.1 --port 8001
pytest
```

## Docker

```bash
docker build -t infradrive/storage-daemon:0.1.0 .
docker run --rm -p 8001:8001 -v infradrive_storage_test:/data infradrive/storage-daemon:0.1.0
```

Для Ansible контейнер запускается без публикации порта и подключается к `infradrive_net`. Внутренний адрес — `http://storage-1:8001` (аналогично `storage-2` и `storage-3`).
