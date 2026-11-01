from __future__ import annotations

from fastapi import FastAPI

from storage_daemon.api.chunks import router as chunks_router
from storage_daemon.config import StorageSettings
from storage_daemon.services.chunk_store import ChunkStore


def create_app(settings: StorageSettings | None = None, store: ChunkStore | None = None) -> FastAPI:
    config = settings or StorageSettings.from_env()
    app = FastAPI(title="InfraDrive Storage Daemon", version="0.1.0")
    app.state.chunk_store = store or ChunkStore(config.data_dir, config.max_chunk_bytes)
    app.include_router(chunks_router)
    return app


app = create_app()
