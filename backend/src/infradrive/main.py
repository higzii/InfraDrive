from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from infradrive.api.files import router as files_router
from infradrive.api.health import router as health_router
from infradrive.config import Settings
from infradrive.metadata.valkey_repository import ValkeyRepository
from infradrive.services.file_service import FileService
from infradrive.storage.client import StorageClient


def create_app(
    settings: Settings | None = None,
    redis_client: Any | None = None,
    storage_client: Any | None = None,
) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owns_redis = redis_client is None
        owns_storage = storage_client is None
        if redis_client is None:
            from redis.asyncio import Redis

            redis = Redis.from_url(config.valkey_url, decode_responses=True)
        else:
            redis = redis_client
        storage = storage_client or StorageClient(
            config.nodes,
            timeout_seconds=config.storage_timeout_seconds,
            connect_timeout_seconds=config.storage_connect_timeout_seconds,
        )
        repository = ValkeyRepository(redis)
        app.state.settings = config
        app.state.redis = redis
        app.state.repository = repository
        app.state.storage = storage
        app.state.file_service = FileService(config, repository, storage)
        try:
            yield
        finally:
            if owns_storage:
                await storage.close()
            if owns_redis:
                await redis.aclose()

    app = FastAPI(
        title="InfraDrive Backend",
        description="Content-addressed distributed file storage API (RF=2)",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Разрешаем CORS со всех источников для фронтенд-песочниц (Vite, Next.js, React)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "Content-Length", "X-Content-SHA256"],
    )

    # Редирект с корня прямо в интерактивную документацию Swagger
    @app.get("/", include_in_schema=False)
    async def root_redirect():
        return RedirectResponse(url="/docs")

    app.include_router(health_router)
    app.include_router(files_router)
    return app


app = create_app()
