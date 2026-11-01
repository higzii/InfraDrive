# Integration notes for the current Ansible dump

The application defaults intentionally line up with the uploaded infrastructure:

| Infrastructure value | Application setting |
|---|---|
| Docker network `infradrive_net` | Backend uses Docker DNS for all internal services |
| Valkey container `infradrive-valkey`, port `6379` | `INFRADRIVE_VALKEY_HOST`, `INFRADRIVE_VALKEY_PORT` |
| Optional `valkey_password` | `INFRADRIVE_VALKEY_PASSWORD` (same value, not hard-coded) |
| Storage containers `storage-1..3` | `INFRADRIVE_STORAGE_NODES` |
| Storage persistent volume mounted at `/data` | `STORAGE_DATA_DIR=/data` |
| Storage internal port `8001` | Docker image exposes `8001` |
| Backend internal port `8000` | Docker image exposes `8000` |
| FastAPI container `infradrive-backend` | existing Ansible role default |

## Deployment details

The storage role is designed for `storage_mode: service`, but will fail closed if `storage_image` is empty. The deployment script exports both real image names and tags before running Ansible. The `stub` mode remains available for infrastructure-only tests.

The backend role does not publish ports by default. The provided deployment helper passes `fastapi_publish_port=true`. In nested-Docker mode the inner backend binds `0.0.0.0:8000`, while the outer `infradrive-target` container must be created with `-p 127.0.0.1:8000:8000`; this outer mapping restricts host access to loopback. Existing containers cannot gain a new published port without recreation (keep the named Docker data volumes). For a direct Debian host, use `INFRADRIVE_FASTAPI_BIND_ADDRESS=127.0.0.1` instead.

If Ansible targets a remote Debian host rather than the local `infradrive-target` container, run the GUI on that host or set the GUI endpoint to a reachable address protected by TLS and authentication. Do not bind the unauthenticated backend to `0.0.0.0` on an untrusted network.

## Existing integration test compatibility

The existing health check uses the expected container and volume names and can run unchanged, but both health/failover scripts must execute inside `infradrive-target` because the nested Docker daemon owns the service containers. Use `deployment/run-tests-in-target.sh` from the host; it copies the scripts and invokes them in the target. The replacement failover script parses `file_id` and the replica pair from JSON and stops an actual replica of the one-chunk test file.
