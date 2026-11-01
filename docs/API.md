# InfraDrive API contract

## Backend (port 8000)

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Valkey + at least RF reachable storage nodes |
| `POST` | `/files` | multipart upload, field `file` |
| `GET` | `/files/{file_id}` | reconstructed binary download |

### Upload response

`201 Created`:

```json
{
  "file_id": "<uuid-hex>",
  "filename": "archive.bin",
  "size": 1048576,
  "sha256": "<64-char-sha256>",
  "chunks": 1,
  "replication_factor": 2,
  "chunk_replicas": [
    {"chunk_id": "<sha256>", "replicas": ["storage-1", "storage-3"]}
  ],
  "status": "ready"
}
```

The replica map is returned for diagnostics and the failover smoke test. It contains only replicas whose PUT returned successfully.

### Failure semantics

- `404` — unknown file ID.
- `401` — token missing/invalid when `INFRADRIVE_API_TOKEN` is configured.
- `413` — configured maximum file size exceeded.
- `503` — Valkey/storage unavailable or RF=2 could not be confirmed.
- `502` — chunk or complete-file integrity check failed.

The full-file SHA-256 is validated before any downloaded bytes are sent. `GET /health` returns `503` if Valkey is unavailable or fewer than RF storage nodes answer health checks.

## Storage daemon (port 8001)

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | checks `/data` write access |
| `PUT` | `/chunks/{chunk_id}` | binary body; SHA-256 must equal `chunk_id` |
| `GET` | `/chunks/{chunk_id}` | binary chunk or `404` |
| `DELETE` | `/chunks/{chunk_id}` | idempotent delete (`204`) |

`chunk_id` is a SHA-256 digest in lowercase hex. Storage writes are staged in `/data` and committed via atomic rename.

## Metadata keys in Valkey

- `file:{file_id}` — JSON manifest with filename, size, full-file SHA-256, ordered chunk list, chunk size, RF, status and timestamp.
- `chunk:{chunk_id}` — JSON chunk metadata with size, SHA-256 and confirmed replica-node names.
- `chunk:{chunk_id}:files` — set of file IDs referencing the chunk.
- `lock:chunk:{chunk_id}` — short-lived Redis lock used to serialize concurrent metadata and replica changes for the same content-addressed chunk.
