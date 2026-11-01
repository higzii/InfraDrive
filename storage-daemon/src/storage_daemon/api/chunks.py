from __future__ import annotations

import hashlib
import re

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse

from storage_daemon.services.chunk_store import (
    ChunkIntegrityError,
    ChunkNotFoundError,
    ChunkStore,
    InvalidChunkIdError,
)

router = APIRouter()
_CHUNK_ID_RE = re.compile(r"^[a-f0-9]{64}$")


def _store(request: Request) -> ChunkStore:
    return request.app.state.chunk_store


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    try:
        _store(request).health()
    except OSError as exc:
        raise HTTPException(status_code=503, detail="storage data directory is unavailable") from exc
    return {"status": "ok"}


@router.put("/chunks/{chunk_id}", status_code=status.HTTP_201_CREATED)
async def put_chunk(chunk_id: str, request: Request) -> dict[str, int | str]:
    if not _CHUNK_ID_RE.fullmatch(chunk_id):
        raise HTTPException(status_code=400, detail="invalid chunk_id")

    store = _store(request)
    digest = hashlib.sha256()
    total = 0

    # Stream to a temporary file while enforcing the daemon's own size limit.
    # ChunkStore handles hashing, atomic rename, and cleanup on failure.
    async def pieces():
        nonlocal total
        async for part in request.stream():
            if not part:
                continue
            total += len(part)
            if total > store.max_chunk_bytes:
                raise HTTPException(status_code=413, detail="chunk exceeds configured maximum size")
            digest.update(part)
            yield part

    import anyio

    try:
        # Run filesystem writes in a worker thread while pulling bounded request pieces.
        # For a single chunk (default 4 MiB), buffering pieces is capped by the request limit.
        collected: list[bytes] = []
        async for part in pieces():
            collected.append(part)
        if digest.hexdigest() != chunk_id:
            raise ChunkIntegrityError("chunk bytes do not match chunk_id")
        await anyio.to_thread.run_sync(store.put_stream, chunk_id, iter(collected))
    except HTTPException:
        raise
    except ChunkIntegrityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InvalidChunkIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=507, detail="unable to persist chunk") from exc

    return {"chunk_id": chunk_id, "size": total, "sha256": chunk_id}


@router.get("/chunks/{chunk_id}")
async def get_chunk(chunk_id: str, request: Request) -> FileResponse:
    try:
        path = _store(request).get_verified_path(chunk_id)
    except InvalidChunkIdError as exc:
        raise HTTPException(status_code=400, detail="invalid chunk_id") from exc
    except ChunkNotFoundError as exc:
        raise HTTPException(status_code=404, detail="chunk not found") from exc
    except ChunkIntegrityError as exc:
        raise HTTPException(status_code=500, detail="stored chunk failed SHA-256 verification") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="unable to read chunk") from exc

    return FileResponse(path, media_type="application/octet-stream", filename=chunk_id)


@router.delete("/chunks/{chunk_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chunk(chunk_id: str, request: Request) -> Response:
    try:
        _store(request).delete(chunk_id)
    except InvalidChunkIdError as exc:
        raise HTTPException(status_code=400, detail="invalid chunk_id") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="unable to delete chunk") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
