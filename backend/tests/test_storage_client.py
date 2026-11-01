import hashlib

import httpx
import pytest

from infradrive.config import StorageNode, Settings
from infradrive.storage.client import StorageClient, StorageNodeError


@pytest.mark.asyncio
async def test_storage_client_requires_matching_put_acknowledgement():
    payload = b"hello"
    chunk_id = hashlib.sha256(payload).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={"chunk_id": chunk_id, "sha256": chunk_id, "size": len(payload)},
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    storage = StorageClient([StorageNode("storage-1", "http://storage-1:8001")], client=http)
    await storage.put_chunk("storage-1", chunk_id, payload)
    await http.aclose()


@pytest.mark.asyncio
async def test_storage_client_rejects_mismatched_put_acknowledgement():
    payload = b"hello"
    chunk_id = hashlib.sha256(payload).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={"chunk_id": "0" * 64, "sha256": "0" * 64, "size": len(payload)},
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    storage = StorageClient([StorageNode("storage-1", "http://storage-1:8001")], client=http)
    with pytest.raises(StorageNodeError):
        await storage.put_chunk("storage-1", chunk_id, payload)
    await http.aclose()


def test_settings_parse_three_ansible_storage_names():
    settings = Settings(
        storage_nodes=(
            "storage-1=http://storage-1:8001,"
            "storage-2=http://storage-2:8001,"
            "storage-3=http://storage-3:8001"
        )
    )
    assert [node.name for node in settings.nodes] == ["storage-1", "storage-2", "storage-3"]
    assert settings.replication_factor == 2
