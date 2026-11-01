from __future__ import annotations

import json
from typing import Any


class ValkeyRepository:
    """Small metadata adapter; file and chunk metadata are kept separately.

    Keys:
      file:{file_id}         -> JSON file manifest
      chunk:{chunk_id}       -> JSON chunk metadata and confirmed replica nodes
      chunk:{chunk_id}:files -> set of file IDs referencing the chunk
      lock:chunk:{chunk_id}  -> short-lived per-chunk distributed lock
    """

    def __init__(self, redis_client: Any) -> None:
        self.redis = redis_client

    async def ping(self) -> bool:
        return bool(await self.redis.ping())

    def chunk_lock(self, chunk_id: str):
        return self.redis.lock(
            f"lock:chunk:{chunk_id}",
            timeout=60,
            blocking_timeout=30,
        )

    async def get_file(self, file_id: str) -> dict[str, Any] | None:
        raw = await self.redis.get(f"file:{file_id}")
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    async def save_file(self, file_id: str, metadata: dict[str, Any]) -> None:
        await self.redis.set(
            f"file:{file_id}",
            json.dumps(metadata, separators=(",", ":"), ensure_ascii=False),
        )

    async def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        raw = await self.redis.get(f"chunk:{chunk_id}")
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    async def chunk_reference_count(self, chunk_id: str) -> int:
        return int(await self.redis.scard(f"chunk:{chunk_id}:files"))

    async def attach_file_to_chunk(
        self,
        chunk_id: str,
        file_id: str,
        metadata: dict[str, Any],
    ) -> None:
        # Keep the chunk manifest and reference set in one Redis transaction.
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.set(
                f"chunk:{chunk_id}",
                json.dumps(metadata, separators=(",", ":")),
            )
            pipe.sadd(f"chunk:{chunk_id}:files", file_id)
            await pipe.execute()

    async def detach_file_from_chunk(
        self,
        chunk_id: str,
        file_id: str,
    ) -> tuple[int, dict[str, Any] | None]:
        # Caller holds the per-chunk lock, so no new reference can be attached
        # between SREM/SCARD and removal of the last-reference metadata.
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.srem(f"chunk:{chunk_id}:files", file_id)
            pipe.scard(f"chunk:{chunk_id}:files")
            _removed, remaining = await pipe.execute()

        metadata = await self.get_chunk(chunk_id)
        if int(remaining) == 0:
            await self.redis.delete(f"chunk:{chunk_id}", f"chunk:{chunk_id}:files")
        return int(remaining), metadata

    async def discard_unreferenced_chunk(self, chunk_id: str) -> None:
        if await self.chunk_reference_count(chunk_id) == 0:
            await self.redis.delete(f"chunk:{chunk_id}", f"chunk:{chunk_id}:files")

    async def delete_file(self, file_id: str) -> None:
        await self.redis.delete(f"file:{file_id}")
