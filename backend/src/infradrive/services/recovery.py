from __future__ import annotations

import hashlib

from infradrive.storage.client import StorageClient, StorageNodeError


class ChunkRecoveryError(RuntimeError):
    pass


class RecoveryService:
    def __init__(self, storage: StorageClient) -> None:
        self.storage = storage

    async def read_chunk(self, chunk_id: str, expected_size: int, replicas: list[str]) -> bytes:
        errors: list[str] = []
        candidates = [name for name in replicas if name in self.storage.nodes]
        for node_name in candidates:
            try:
                data = await self.storage.get_chunk(node_name, chunk_id)
                if len(data) != expected_size:
                    raise ChunkRecoveryError(
                        f"chunk size mismatch from {node_name}: expected {expected_size}, got {len(data)}"
                    )
                if hashlib.sha256(data).hexdigest() != chunk_id:
                    raise ChunkRecoveryError(f"chunk checksum mismatch from {node_name}")
                return data
            except (StorageNodeError, ChunkRecoveryError) as exc:
                errors.append(f"{node_name}: {exc}")
        raise ChunkRecoveryError(
            f"all replicas failed for chunk {chunk_id}: {'; '.join(errors) or 'no replicas recorded'}"
        )
