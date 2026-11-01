# File-by-file layout

## `storage-daemon/`

- `Dockerfile` — compact Python image, non-root runtime user, `/data` volume, HTTP healthcheck.
- `pyproject.toml` — runtime and test dependencies.
- `src/storage_daemon/config.py` — data directory, port and chunk-size configuration.
- `src/storage_daemon/main.py` — FastAPI app factory and router registration.
- `src/storage_daemon/api/chunks.py` — `PUT`, `GET`, `DELETE /chunks/{chunk_id}` and `/health`.
- `src/storage_daemon/services/chunk_store.py` — safe SHA-256 paths, atomic writes and persistent filesystem storage.
- `tests/test_chunk_store.py`, `tests/test_chunks.py` — filesystem and HTTP contract tests.

## `backend/`

- `Dockerfile` — FastAPI runtime image.
- `pyproject.toml` — FastAPI, HTTPX, Redis/Valkey and multipart dependencies.
- `src/infradrive/config.py` — environment-driven settings and storage node parsing.
- `src/infradrive/main.py` — app lifecycle, Valkey and storage client wiring.
- `src/infradrive/api/files.py` — upload/download endpoints, API token check and integrity error mapping.
- `src/infradrive/api/health.py` — Valkey and storage availability check.
- `src/infradrive/metadata/valkey_repository.py` — file/chunk metadata, references and per-chunk lock.
- `src/infradrive/storage/client.py` — HTTP calls to storage daemon and PUT acknowledgement validation.
- `src/infradrive/services/chunker.py` — chunk and SHA helpers.
- `src/infradrive/services/replication.py` — confirmed RF=2 placement across distinct nodes.
- `src/infradrive/services/recovery.py` — replica fallback and per-chunk checksum validation.
- `src/infradrive/services/file_service.py` — streaming upload, rollback, metadata commit and verified download reconstruction.
- `tests/` — API, configuration, replication failure, recovery and storage-client tests.

## `desktop-client/`

- `infradrive_gui.py` — standalone Tkinter app with endpoint/token fields, health, upload and download.

## `deployment/`

- `ansible-group-vars-additions.yml` — env mapping for Valkey and the three storage nodes; healthcheck settings.
- `build-and-deploy.sh` — source copy, image build in nested Docker and Ansible deployment.
- `test_failover.sh` — in-target RF=2 failover smoke test.
- `run-tests-in-target.sh` — host-side wrapper for health/failover tests against the nested Docker daemon.
