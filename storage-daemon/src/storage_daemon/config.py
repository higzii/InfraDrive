from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StorageSettings:
    data_dir: Path
    max_chunk_bytes: int
    host: str
    port: int

    @classmethod
    def from_env(cls) -> "StorageSettings":
        max_chunk_bytes = int(os.getenv("STORAGE_MAX_CHUNK_BYTES", str(4 * 1024 * 1024)))
        if max_chunk_bytes <= 0:
            raise ValueError("STORAGE_MAX_CHUNK_BYTES must be greater than zero")

        port = int(os.getenv("STORAGE_PORT", "8001"))
        if not 1 <= port <= 65535:
            raise ValueError("STORAGE_PORT must be between 1 and 65535")

        return cls(
            data_dir=Path(os.getenv("STORAGE_DATA_DIR", "/data")),
            max_chunk_bytes=max_chunk_bytes,
            host=os.getenv("STORAGE_HOST", "0.0.0.0"),
            port=port,
        )
