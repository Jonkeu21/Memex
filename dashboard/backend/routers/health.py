"""Liveness + readiness probes."""
from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request) -> JSONResponse:
    """Probe SQLite reachability + vault directory existence.

    Returns 200 with ``{"status":"ok",...}`` when both checks pass, 503
    with ``{"status":"not_ready", "checks":{...}}`` otherwise.
    """
    settings = request.app.state.settings
    checks: dict[str, Any] = {}
    ok = True
    try:
        conn: sqlite3.Connection = request.app.state.db
        conn.execute("SELECT 1").fetchone()
        checks["db"] = "ok"
    except sqlite3.Error as exc:
        checks["db"] = f"error: {exc}"
        ok = False
    if settings.vault_dir.is_dir():
        checks["vault"] = "ok"
    else:
        checks["vault"] = f"missing: {settings.vault_dir}"
        ok = False
    payload = {"status": "ok" if ok else "not_ready", "checks": checks}
    code = status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(payload, status_code=code)
