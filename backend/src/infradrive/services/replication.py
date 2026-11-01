from __future__ import annotations

import hashlib
from typing import Any

from infradrive.config import Settings
from infradrive.storage.client import StorageClient, StorageNodeError


class ReplicationError(RuntimeError):
    def __init__(self, chunk_id: str, confirmed: list[str], errors: list[str]) -> None:
        self.chunk_id = chunk_id
        self.confirmed = confirmed
        self.errors = errors
        super().__init__(
            f"RF={len(confirmed)} replication failed for chunk {chunk_id}; "
            f"confirmed={confirmed}; errors={errors}"
        )


class ReplicationService:
    def __init__(self, settings: Settings, storage: StorageClient) -> None:
        self.settings = settings
        self.storage = storage

    def _candidate_order(self, chunk_id: str, existing_replicas: list[str] | None = None) -> list[str]:
        names = self.storage.node_names()
        if not names:
            return []
        digest_index = int(hashlib.sha256(chunk_id.encode("ascii")).hexdigest(), 16) % len(names)
        rotated = names[digest_index:] + names[:digest_index]
        preferred = [name for name in (existing_replicas or []) if name in self.storage.nodes]
        return preferred + [name for name in rotated if name not in preferred]

    async def ensure_replicas(
        self,
        chunk_id: str,
        data: bytes,
        existing_metadata: dict[str, Any] | None = None,
    ) -> list[str]:
        existing_nodes = list((existing_metadata or {}).get("replicas", []))
        confirmed: list[str] = []
        errors: list[str] = []

        for node_name in self._candidate_order(chunk_id, existing_nodes):
            try:
                # A confirmed PUT is the only event that may enter the metadata map.
                await self.storage.put_chunk(node_name, chunk_id, data)
                confirmed.append(node_name)
            except StorageNodeError as exc:
                errors.append(str(exc))
            if len(confirmed) >= self.settings.replication_factor:
                break

        if len(confirmed) < self.settings.replication_factor:
            raise ReplicationError(chunk_id, confirmed, errors)
        return confirmed
