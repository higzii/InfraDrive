FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STORAGE_HOST=0.0.0.0 \
    STORAGE_PORT=8001 \
    STORAGE_DATA_DIR=/data \
    STORAGE_MAX_CHUNK_BYTES=4194304

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && mkdir -p /data \
    && useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin storage \
    && chown -R storage:storage /app /data

USER storage
EXPOSE 8001
VOLUME ["/data"]
HEALTHCHECK --interval=15s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=3)" || exit 1
CMD ["uvicorn", "storage_daemon.main:app", "--host", "0.0.0.0", "--port", "8001"]
