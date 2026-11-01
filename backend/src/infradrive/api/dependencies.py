from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status

from infradrive.services.file_service import FileService


def get_file_service(request: Request) -> FileService:
    return request.app.state.file_service


async def require_api_token(request: Request) -> None:
    expected = request.app.state.settings.api_token
    if not expected:
        return
    authorization = request.headers.get("Authorization", "")
    supplied = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
