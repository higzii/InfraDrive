from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from infradrive.api.dependencies import get_file_service, require_api_token
from infradrive.services.file_service import (
    FileIntegrityError,
    FileMetadataNotFoundError,
    FileService,
    UploadTooLargeError,
)
from infradrive.services.recovery import ChunkRecoveryError
from infradrive.services.replication import ReplicationError

router = APIRouter(prefix="/files", tags=["files"], dependencies=[Depends(require_api_token)])


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    service: FileService = Depends(get_file_service),
) -> dict:
    try:
        manifest = await service.upload(file)
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ReplicationError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "unable to confirm the required number of chunk replicas",
                "chunk_id": exc.chunk_id,
                "confirmed_replicas": exc.confirmed,
                "errors": exc.errors,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="file upload could not be committed") from exc

    return {
        "file_id": manifest["file_id"],
        "filename": manifest["filename"],
        "size": manifest["size"],
        "sha256": manifest["sha256"],
        "chunks": len(manifest["chunks"]),
        "replication_factor": manifest["replication_factor"],
        # Included for diagnostics and the failover test; the first chunk's
        # replica pair can be stopped safely when the test payload is one chunk.
        "chunk_replicas": [
            {"chunk_id": item["chunk_id"], "replicas": item["replicas"]}
            for item in manifest["chunks"]
        ],
        "status": manifest["status"],
    }


@router.get("/{file_id}")
async def download_file(
    file_id: str,
    service: FileService = Depends(get_file_service),
) -> StreamingResponse:
    try:
        result = await service.download(file_id)
    except FileMetadataNotFoundError as exc:
        raise HTTPException(status_code=404, detail="file not found") from exc
    except ChunkRecoveryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FileIntegrityError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="file could not be reconstructed") from exc

    ascii_name = result.filename.encode("ascii", "ignore").decode("ascii") or "download.bin"
    ascii_name = ascii_name.replace("\\", "_").replace('"', "_")
    encoded_name = quote(result.filename, safe="")
    headers = {
        "Content-Disposition": f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}',
        "Content-Length": str(result.size),
        "X-Content-SHA256": result.sha256,
    }

    def stream_file():
        try:
            while True:
                piece = result.file.read(1024 * 1024)
                if not piece:
                    break
                yield piece
        finally:
            result.file.close()

    return StreamingResponse(
        stream_file(),
        media_type="application/octet-stream",
        headers=headers,
        background=BackgroundTask(result.file.close),
    )
