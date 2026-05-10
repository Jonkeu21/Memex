"""Bearer-token authentication for mutating dashboard endpoints.

The dashboard uses a single shared bearer token (``MEMEX_DASHBOARD_BEARER_TOKEN``).
Read-only endpoints are open on the tailnet; the token is required only for
mutating actions (queue retry/cancel, inbox routing/delete, taxonomy save,
retrieval).

The capture API uses a label-keyed token map; the dashboard intentionally does
not — it is single-user, and the token is the second factor behind Tailscale.
"""
from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from .config import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def require_token(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Return the validated bearer token; raise 401 otherwise.

    Comparison is constant-time via :func:`secrets.compare_digest`. The
    expected token comes from the dashboard's startup config and never changes
    across the process lifetime.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "missing bearer token"}},
            headers={"WWW-Authenticate": "Bearer"},
        )
    scheme, _, presented = authorization.partition(" ")
    if scheme.lower() != "bearer" or not presented:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "expected 'Bearer <token>'"}},
            headers={"WWW-Authenticate": "Bearer"},
        )
    expected = settings.bearer_token
    presented_b = presented.encode("utf-8")
    expected_b = expected.encode("utf-8")
    if len(presented_b) != len(expected_b):
        # Run a comparison anyway so timing does not leak length info.
        secrets.compare_digest(expected_b, expected_b)
        ok = False
    else:
        ok = secrets.compare_digest(presented_b, expected_b)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "invalid token"}},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return presented
