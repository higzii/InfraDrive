# InfraDrive FastAPI Backend

Backend координирует загрузку и скачивание файлов, делит содержимое на chunks по 4 MiB, считает SHA-256, подтверждает две копии на разных storage-нодах и хранит manifests в Valkey.

## API

### `POST /files`

`multipart/form-data`, поле `file`.

Успех — HTTP `201` и JSON с `file_id`, `filename`, `size`, `sha256`, количеством chunks и `replication_factor`. Успех возвращается только после подтверждённых RF=2 PUT-операций и записи metadata в Valkey.

### `GET /files/{file_id}`

Возвращает исходный бинарный файл. Сервис пытается читать каждую часть с первой реплики, затем со второй. Полный размер и SHA-256 проверяются до начала HTTP-ответа; при ошибке не отдаётся частично собранный файл.

### `GET /health`

Проверяет Valkey и наличие минимум `RF` доступных storage-нод. При проблеме возвращает `503`.

### Защита API

Если задан `INFRADRIVE_API_TOKEN`, операции `/files` требуют заголовок `Authorization: Bearer <token>`. Health endpoint оставлен доступным для Docker healthcheck.

## Локальный запуск backend

Нужен доступный Valkey и три storage daemon (или минимум RF=2 доступных узла).

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
export INFRADRIVE_VALKEY_HOST=127.0.0.1
export INFRADRIVE_STORAGE_NODES='storage-1=http://127.0.0.1:8001,storage-2=http://127.0.0.1:8002,storage-3=http://127.0.0.1:8003'
uvicorn infradrive.main:app --host 127.0.0.1 --port 8000
pytest
```

В локальном режиме опубликуй storage daemon на host-порты 8001–8003. В целевой Ansible-сети публикация storage-портов не нужна: backend использует DNS-имена Docker network.
