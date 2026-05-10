"""Liveness and readiness."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from ..auth import Principal, get_settings, require_token
from ..config import Settings
from ..db import is_writable

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[Principal, Depends(require_token)],
) -> dict[str, str]:
    if is_writable(settings.db_path):
        return {"status": "ok"}
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "unavailable"}
