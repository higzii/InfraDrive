import hashlib

import pytest

from infradrive.services.recovery import ChunkRecoveryError, RecoveryService
from tests.fakes import FakeStorage


@pytest.mark.asyncio
async def test_recovery_checks_digest_and_tries_second_replica():
    payload = b"recovery-test"
    chunk_id = hashlib.sha256(payload).hexdigest()
    storage = FakeStorage(["storage-1", "storage-2", "storage-3"])
    storage.data["storage-1"][chunk_id] = b"corrupt"
    storage.data["storage-2"][chunk_id] = payload

    result = await RecoveryService(storage).read_chunk(
        chunk_id, len(payload), ["storage-1", "storage-2"]
    )
    assert result == payload


@pytest.mark.asyncio
async def test_recovery_fails_when_all_replicas_are_unavailable():
    payload = b"recovery-test"
    chunk_id = hashlib.sha256(payload).hexdigest()
    storage = FakeStorage(["storage-1", "storage-2"])
    storage.online.clear()
    with pytest.raises(ChunkRecoveryError):
        await RecoveryService(storage).read_chunk(chunk_id, len(payload), ["storage-1", "storage-2"])
