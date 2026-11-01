FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INFRADRIVE_VALKEY_HOST=infradrive-valkey \
    INFRADRIVE_VALKEY_PORT=6379 \
    INFRADRIVE_STORAGE_NODES=storage-1=http://storage-1:8001,storage-2=http://storage-2:8001,storage-3=http://storage-3:8001 \
    INFRADRIVE_CHUNK_SIZE_BYTES=4194304 \
    INFRADRIVE_REPLICATION_FACTOR=2

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin infradrive

USER infradrive
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1
CMD ["uvicorn", "infradrive.main:app", "--host", "0.0.0.0", "--port", "8000"]
