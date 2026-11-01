from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path


_CHUNK_ID_RE = re.compile(r"^[a-f0-9]{64}$")


class ChunkNotFoundError(FileNotFoundError):
    pass


class InvalidChunkIdError(ValueError):
    pass


class ChunkIntegrityError(ValueError):
    pass


class ChunkStore:
    """Filesystem-backed, content-addressed chunk store.

    Chunk IDs are SHA-256 hex digests, never paths supplied by a caller.
    Writes are staged in the same directory and atomically renamed.
    """

    def __init__(self, data_dir: Path | str, max_chunk_bytes: int = 4 * 1024 * 1024) -> None:
        self.root = Path(data_dir).expanduser().resolve()
        self.max_chunk_bytes = max_chunk_bytes
        if max_chunk_bytes <= 0:
            raise ValueError("max_chunk_bytes must be greater than zero")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, chunk_id: str) -> Path:
        if not isinstance(chunk_id, str) or not _CHUNK_ID_RE.fullmatch(chunk_id):
            raise InvalidChunkIdError("chunk_id must be a 64-character lowercase SHA-256 hex digest")
        path = self.root / chunk_id
        if path.parent != self.root:
            raise InvalidChunkIdError("invalid chunk_id")
        return path

    def put_stream(self, chunk_id: str, chunks) -> int:
        destination = self._path_for(chunk_id)
        digest = hashlib.sha256()
        total = 0
        fd = -1
        temporary_path: str | None = None

        try:
            fd, temporary_path = tempfile.mkstemp(prefix=".chunk-", suffix=".tmp", dir=self.root)
            with os.fdopen(fd, "wb") as temporary_file:
                fd = -1
                for piece in chunks:
                    if not piece:
                        continue
                    total += len(piece)
                    if total > self.max_chunk_bytes:
                        raise ValueError("chunk exceeds configured maximum size")
                    digest.update(piece)
                    temporary_file.write(piece)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            if digest.hexdigest() != chunk_id:
                raise ChunkIntegrityError("chunk bytes do not match chunk_id")

            # Replace is atomic when source and destination are on the same filesystem.
            os.replace(temporary_path, destination)
            temporary_path = None
            return total
        finally:
            if fd >= 0:
                os.close(fd)
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass

    def put_bytes(self, chunk_id: str, data: bytes) -> int:
        return self.put_stream(chunk_id, (data,))

    def get_path(self, chunk_id: str) -> Path:
        path = self._path_for(chunk_id)
        try:
            stat = path.lstat()
        except FileNotFoundError as exc:
            raise ChunkNotFoundError(chunk_id) from exc
        # Do not follow symlinks placed in the data directory.
        if not path.is_file() or path.is_symlink():
            raise ChunkNotFoundError(chunk_id)
        if stat.st_size > self.max_chunk_bytes:
            raise OSError("stored chunk exceeds configured maximum size")
        return path

    def get_verified_path(self, chunk_id: str) -> Path:
        path = self.get_path(chunk_id)
        with path.open("rb") as source:
            actual_digest = hashlib.file_digest(source, "sha256").hexdigest()
        if actual_digest != chunk_id:
            raise ChunkIntegrityError("stored chunk failed SHA-256 verification")
        return path

    def read_bytes(self, chunk_id: str) -> bytes:
        path = self.get_verified_path(chunk_id)
        return path.read_bytes()

    def delete(self, chunk_id: str) -> bool:
        path = self._path_for(chunk_id)
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False

    def health(self) -> bool:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, probe = tempfile.mkstemp(prefix=".health-", dir=self.root)
        try:
            os.close(fd)
            os.unlink(probe)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        return True
