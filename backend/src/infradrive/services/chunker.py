from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator


def iter_chunks(data: bytes, chunk_size: int) -> Iterator[bytes]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    for offset in range(0, len(data), chunk_size):
        yield data[offset : offset + chunk_size]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_stream(chunks: Iterable[bytes]) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    for chunk in chunks:
        digest.update(chunk)
        total += len(chunk)
    return digest.hexdigest(), total
