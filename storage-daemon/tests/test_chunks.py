import hashlib

from fastapi.testclient import TestClient

from storage_daemon.config import StorageSettings
from storage_daemon.main import create_app
from storage_daemon.services.chunk_store import ChunkStore


def test_chunk_http_contract(tmp_path):
    store = ChunkStore(tmp_path, max_chunk_bytes=1024)
    settings = StorageSettings(tmp_path, 1024, "127.0.0.1", 8001)
    client = TestClient(create_app(settings=settings, store=store))
    payload = b"binary\x00payload"
    chunk_id = hashlib.sha256(payload).hexdigest()

    response = client.put(f"/chunks/{chunk_id}", content=payload)
    assert response.status_code == 201
    assert response.json()["sha256"] == chunk_id

    response = client.get(f"/chunks/{chunk_id}")
    assert response.status_code == 200
    assert response.content == payload

    assert client.get("/chunks/../bad").status_code in (404, 400)
    assert client.get(f"/chunks/{'0' * 64}").status_code == 404
    assert client.delete(f"/chunks/{chunk_id}").status_code == 204
    assert client.delete(f"/chunks/{chunk_id}").status_code == 204
    assert client.get("/health").json() == {"status": "ok"}


def test_wrong_digest_is_rejected(tmp_path):
    store = ChunkStore(tmp_path, max_chunk_bytes=1024)
    app = create_app(StorageSettings(tmp_path, 1024, "127.0.0.1", 8001), store=store)
    client = TestClient(app)
    response = client.put(f"/chunks/{'0' * 64}", content=b"not that hash")
    assert response.status_code == 422
    assert list(tmp_path.iterdir()) == []


def test_chunk_http_rejects_oversized_request(tmp_path):
    store = ChunkStore(tmp_path, max_chunk_bytes=4)
    app = create_app(StorageSettings(tmp_path, 4, "127.0.0.1", 8001), store=store)
    client = TestClient(app)
    payload = b"12345"
    chunk_id = hashlib.sha256(payload).hexdigest()
    response = client.put(f"/chunks/{chunk_id}", content=payload)
    assert response.status_code == 413
    assert list(tmp_path.iterdir()) == []


def test_get_rejects_corrupted_stored_chunk(tmp_path):
    store = ChunkStore(tmp_path, max_chunk_bytes=1024)
    payload = b"original"
    chunk_id = hashlib.sha256(payload).hexdigest()
    store.put_bytes(chunk_id, payload)
    (tmp_path / chunk_id).write_bytes(b"corrupted")
    client = TestClient(create_app(StorageSettings(tmp_path, 1024, "127.0.0.1", 8001), store=store))
    response = client.get(f"/chunks/{chunk_id}")
    assert response.status_code == 500
