from __future__ import annotations

import hashlib
import logging
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePath
from typing import Any, BinaryIO

from infradrive.config import Settings
from infradrive.metadata.valkey_repository import ValkeyRepository
from infradrive.services.recovery import ChunkRecoveryError, RecoveryService
from infradrive.services.replication import ReplicationError, ReplicationService
from infradrive.storage.client import StorageClient

logger = logging.getLogger(__name__)


class UploadTooLargeError(ValueError):
    pass


class FileMetadataNotFoundError(FileNotFoundError):
    pass


class FileIntegrityError(RuntimeError):
    pass


@dataclass(slots=True)
class DownloadResult:
    file: BinaryIO
    filename: str
    size: int
    sha256: str


class FileService:
    def __init__(
        self,
        settings: Settings,
        repository: ValkeyRepository,
        storage: StorageClient,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.storage = storage
        self.replication = ReplicationService(settings, storage)
        self.recovery = RecoveryService(storage)

    @staticmethod
    def safe_filename(filename: str | None) -> str:
        name = PurePath((filename or "upload.bin").replace("\\", "/")).name
        name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
        return (name or "upload.bin")[:255]

    async def upload(self, upload_file: Any) -> dict[str, Any]:
        file_id = uuid.uuid4().hex
        filename = self.safe_filename(getattr(upload_file, "filename", None))
        file_digest = hashlib.sha256()
        file_size = 0
        chunks: list[dict[str, Any]] = []
        referenced_chunk_ids: list[str] = []
        referenced_seen: set[str] = set()

        try:
            while True:
                data = await upload_file.read(self.settings.chunk_size_bytes)
                if not data:
                    break

                file_size += len(data)
                if file_size > self.settings.max_file_bytes:
                    raise UploadTooLargeError(
                        f"file exceeds configured maximum of {self.settings.max_file_bytes} bytes"
                    )
                file_digest.update(data)
                chunk_id = hashlib.sha256(data).hexdigest()

                async with self.repository.chunk_lock(chunk_id):
                    existing_metadata = await self.repository.get_chunk(chunk_id)
                    try:
                        replicas = await self.replication.ensure_replicas(
                            chunk_id,
                            data,
                            existing_metadata=existing_metadata,
                        )
                    except ReplicationError as exc:
                        # A failed new chunk may have one confirmed copy. Remove it only
                        # when no completed file references the chunk yet.
                        if await self.repository.chunk_reference_count(chunk_id) == 0:
                            candidate_nodes = set(exc.confirmed)
                            if existing_metadata:
                                candidate_nodes.update(existing_metadata.get("replicas", []))
                            for node_name in candidate_nodes:
                                try:
                                    await self.storage.delete_chunk(node_name, chunk_id)
                                except Exception:
                                    logger.warning("Unable to clean partial chunk %s from %s", chunk_id, node_name)
                            await self.repository.discard_unreferenced_chunk(chunk_id)
                        raise

                    chunk_metadata = {
                        "chunk_id": chunk_id,
                        "sha256": chunk_id,
                        "size": len(data),
                        "replicas": replicas,
                    }
                    if chunk_id not in referenced_seen:
                        # Track before metadata writes so rollback can clean up a partial
                        # SET/SADD failure as well.
                        referenced_seen.add(chunk_id)
                        referenced_chunk_ids.append(chunk_id)
                    try:
                        await self.repository.attach_file_to_chunk(chunk_id, file_id, chunk_metadata)
                    except Exception:
                        if await self.repository.chunk_reference_count(chunk_id) == 0:
                            for node_name in replicas:
                                try:
                                    await self.storage.delete_chunk(node_name, chunk_id)
                                except Exception:
                                    logger.warning(
                                        "Unable to clean chunk %s from %s after metadata failure",
                                        chunk_id,
                                        node_name,
                                    )
                            await self.repository.discard_unreferenced_chunk(chunk_id)
                        raise

                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "size": len(data),
                        "sha256": chunk_id,
                        "replicas": replicas,
                    }
                )

            manifest = {
                "file_id": file_id,
                "filename": filename,
                "size": file_size,
                "sha256": file_digest.hexdigest(),
                "chunk_size": self.settings.chunk_size_bytes,
                "replication_factor": self.settings.replication_factor,
                "chunks": chunks,
                "status": "ready",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await self.repository.save_file(file_id, manifest)
            return manifest
        except Exception:
            await self._rollback_upload(file_id, referenced_chunk_ids)
            raise
        finally:
            close = getattr(upload_file, "close", None)
            if close is not None:
                await close()

    async def _rollback_upload(self, file_id: str, chunk_ids: list[str]) -> None:
        try:
            await self.repository.delete_file(file_id)
        except Exception:
            logger.exception("Unable to remove incomplete file metadata for %s", file_id)

        for chunk_id in reversed(chunk_ids):
            try:
                async with self.repository.chunk_lock(chunk_id):
                    remaining, metadata = await self.repository.detach_file_from_chunk(chunk_id, file_id)
                    if remaining == 0 and metadata:
                        for node_name in metadata.get("replicas", []):
                            try:
                                await self.storage.delete_chunk(node_name, chunk_id)
                            except Exception:
                                logger.warning(
                                    "Unable to remove orphan chunk %s from %s",
                                    chunk_id,
                                    node_name,
                                )
            except Exception:
                logger.exception("Unable to roll back chunk %s for file %s", chunk_id, file_id)

    async def download(self, file_id: str) -> DownloadResult:
        manifest = await self.repository.get_file(file_id)
        if not manifest or manifest.get("status") != "ready":
            raise FileMetadataNotFoundError(file_id)

        spool = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
        digest = hashlib.sha256()
        total_size = 0
        try:
            for descriptor in manifest.get("chunks", []):
                chunk_id = descriptor["chunk_id"]
                current_chunk_metadata = await self.repository.get_chunk(chunk_id)
                # A later upload may have repaired/rebalanced this content-addressed
                # chunk. Use the current replica map first, then the manifest's map
                # as a fallback for older file records.
                current_replicas = list((current_chunk_metadata or {}).get("replicas", []))
                manifest_replicas = list(descriptor.get("replicas", []))
                replicas = list(dict.fromkeys(current_replicas + manifest_replicas))
                data = await self.recovery.read_chunk(
                    chunk_id,
                    int(descriptor["size"]),
                    replicas,
                )
                spool.write(data)
                digest.update(data)
                total_size += len(data)

            if total_size != int(manifest["size"]):
                raise FileIntegrityError("reconstructed file size does not match metadata")
            if digest.hexdigest() != manifest["sha256"]:
                raise FileIntegrityError("reconstructed file SHA-256 does not match metadata")

            spool.seek(0)
            return DownloadResult(
                file=spool,
                filename=self.safe_filename(manifest.get("filename")),
                size=total_size,
                sha256=digest.hexdigest(),
            )
        except Exception:
            spool.close()
            raise
