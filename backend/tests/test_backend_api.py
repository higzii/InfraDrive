from __future__ import annotations

import hashlib
from contextlib import contextmanager

from fastapi.testclient import TestClient

from infradrive.config import Settings
from infradrive.main import create_app
from tests.fakes import FakeRedis, FakeStorage


@contextmanager
def make_client(*, token: str = ""):
    names = ["storage-1", "storage-2", "storage-3"]
    settings = Settings(
        storage_nodes=",".join(f"{name}=http://{name}:8001" for name in names),
        chunk_size_bytes=5,
        max_file_bytes=1024,
        replication_factor=2,
        api_token=token,
    )
    redis = FakeRedis()
    storage = FakeStorage(names)
    app = create_app(settings=settings, redis_client=redis, storage_client=storage)
    with TestClient(app) as client:
        yield client, redis, storage


def test_upload_download_and_read_from_second_replica():
    with make_client() as (client, _redis, storage):
        payload = b"binary\x00content crossing multiple chunks"

        response = client.post(
            "/files",
            files={"file": ("test.bin", payload, "application/octet-stream")},
        )
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["status"] == "ready"
        assert result["replication_factor"] == 2
        assert result["sha256"] == hashlib.sha256(payload).hexdigest()
        assert result["chunks"] > 1

        # Disable one of the two physical copies of the first chunk. Download must
        # fall back to its other replica and still return the original file.
        chunk_id = hashlib.sha256(payload[:5]).hexdigest()
        nodes_with_chunk = [name for name, chunks in storage.data.items() if chunk_id in chunks]
        assert len(nodes_with_chunk) == 2
        storage.online.remove(nodes_with_chunk[0])

        download = client.get(f"/files/{result['file_id']}")
        assert download.status_code == 200, download.text
        assert download.content == payload
        assert download.headers["x-content-sha256"] == hashlib.sha256(payload).hexdigest()


def test_upload_fails_when_rf2_cannot_be_confirmed():
    with make_client() as (client, redis, storage):
        storage.online = {"storage-1"}

        response = client.post(
            "/files",
            files={"file": ("one.bin", b"not enough replicas", "application/octet-stream")},
        )
        assert response.status_code == 503
        assert "confirmed_replicas" in response.json()["detail"]
        assert not any(key.startswith("file:") for key in redis.values)
        assert all(not chunks for chunks in storage.data.values())


def test_empty_file_is_a_valid_file():
    with make_client() as (client, _redis, _storage):
        response = client.post("/files", files={"file": ("empty.bin", b"", "application/octet-stream")})
        assert response.status_code == 201
        file_id = response.json()["file_id"]
        download = client.get(f"/files/{file_id}")
        assert download.status_code == 200
        assert download.content == b""


def test_api_token_is_optional_but_enforced_when_configured():
    with make_client(token="test-secret") as (client, _redis, _storage):
        no_token = client.post("/files", files={"file": ("a.bin", b"x", "application/octet-stream")})
        assert no_token.status_code == 401
        good_token = client.post(
            "/files",
            headers={"Authorization": "Bearer test-secret"},
            files={"file": ("a.bin", b"x", "application/octet-stream")},
        )
        assert good_token.status_code == 201
        assert client.get("/health").status_code == 200


def test_health_requires_valkey_and_at_least_rf_nodes():
    with make_client() as (client, _redis, storage):
        assert client.get("/health").status_code == 200
        storage.online = {"storage-1"}
        assert client.get("/health").status_code == 503


def test_old_manifest_uses_repaired_current_replica_map():
    with make_client() as (client, _redis, storage):
        payload = b"12345"
        first = client.post(
            "/files",
            files={"file": ("first.bin", payload, "application/octet-stream")},
        ).json()
        chunk_id = hashlib.sha256(payload).hexdigest()
        first_pair = [name for name, chunks in storage.data.items() if chunk_id in chunks]
        assert len(first_pair) == 2

        # A later upload repairs the chunk from the remaining copy onto the third node.
        storage.online.remove(first_pair[0])
        second_response = client.post(
            "/files",
            files={"file": ("second.bin", payload, "application/octet-stream")},
        )
        assert second_response.status_code == 201
        second_pair = [name for name, chunks in storage.data.items() if chunk_id in chunks and name in storage.online]
        assert len(second_pair) == 2

        # The first file's manifest has the old pair. The chunk metadata is newer;
        # the backend should use that current map to survive another replica outage.
        storage.online.remove(second_pair[0])
        download = client.get(f"/files/{first['file_id']}")
        assert download.status_code == 200
        assert download.content == payload
