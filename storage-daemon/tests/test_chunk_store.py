import hashlib

import pytest

from storage_daemon.services.chunk_store import (
    ChunkIntegrityError,
    ChunkNotFoundError,
    ChunkStore,
    InvalidChunkIdError,
)


def test_put_get_delete_and_idempotent_put(tmp_path):
    data = b"infradrive chunk data"
    chunk_id = hashlib.sha256(data).hexdigest()
    store = ChunkStore(tmp_path)

    assert store.put_bytes(chunk_id, data) == len(data)
    assert store.get_path(chunk_id).read_bytes() == data
    assert store.put_bytes(chunk_id, data) == len(data)
    assert store.read_bytes(chunk_id) == data
    assert store.delete(chunk_id) is True
    assert store.delete(chunk_id) is False
    with pytest.raises(ChunkNotFoundError):
        store.read_bytes(chunk_id)


def test_data_survives_store_recreation(tmp_path):
    data = b"persistent volume"
    chunk_id = hashlib.sha256(data).hexdigest()
    ChunkStore(tmp_path).put_bytes(chunk_id, data)
    assert ChunkStore(tmp_path).read_bytes(chunk_id) == data


@pytest.mark.parametrize("chunk_id", ["../etc/passwd", "a" * 63, "G" * 64, ""])
def test_rejects_invalid_chunk_ids(tmp_path, chunk_id):
    with pytest.raises(InvalidChunkIdError):
        ChunkStore(tmp_path).get_path(chunk_id)


def test_rejects_content_with_wrong_digest(tmp_path):
    store = ChunkStore(tmp_path)
    expected = hashlib.sha256(b"expected").hexdigest()
    with pytest.raises(ChunkIntegrityError):
        store.put_bytes(expected, b"different")
    assert list(tmp_path.iterdir()) == []


def test_enforces_chunk_size(tmp_path):
    store = ChunkStore(tmp_path, max_chunk_bytes=4)
    chunk_id = hashlib.sha256(b"12345").hexdigest()
    with pytest.raises(ValueError):
        store.put_bytes(chunk_id, b"12345")
    assert list(tmp_path.iterdir()) == []
