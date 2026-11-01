from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict:
    settings = request.app.state.settings
    repository = request.app.state.repository
    storage = request.app.state.storage

    try:
        await repository.ping()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"status": "degraded", "valkey": "unavailable"},
        ) from exc

    node_names = storage.node_names()
    node_states = await asyncio.gather(*(storage.health(name) for name in node_names))
    state_map = {name: ("ok" if available else "unavailable") for name, available in zip(node_names, node_states)}
    available_count = sum(node_states)
    if available_count < settings.replication_factor:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "degraded",
                "valkey": "ok",
                "storage": state_map,
                "available_storage_nodes": available_count,
                "required_storage_nodes": settings.replication_factor,
            },
        )

    return {
        "status": "ok",
        "valkey": "ok",
        "storage": state_map,
        "available_storage_nodes": available_count,
        "replication_factor": settings.replication_factor,
    }
