import hashlib

import pytest

from infradrive.services.chunker import digest_stream, iter_chunks, sha256_hex


def test_iter_chunks_preserves_order_and_bytes():
    assert list(iter_chunks(b"abcdefgh", 3)) == [b"abc", b"def", b"gh"]


def test_digest_stream_matches_hashlib():
    expected = hashlib.sha256(b"abccde").hexdigest()
    assert digest_stream([b"abc", b"cde"]) == (expected, 6)
    assert sha256_hex(b"payload") == hashlib.sha256(b"payload").hexdigest()


def test_rejects_non_positive_chunk_size():
    with pytest.raises(ValueError):
        list(iter_chunks(b"abc", 0))
