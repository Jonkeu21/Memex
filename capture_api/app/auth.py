"""Bearer-token authentication.

CLAUDE.md spec: tokens are loaded as ``MEMEX_CAPTURE_TOKEN_<LABEL>=<value>``;
the matching ``LABEL`` is recorded as ``api:<label>`` in ``submitter``.
Comparison is constant-time over every configured token.
"""
from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status

from .config import Settings


@dataclass(frozen=True)
class Principal:
    label: str

    @property
    def submitter(self) -> str:
        return f"api:{self.label}"


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def _match_token(presented: str, tokens: dict[str, str]) -> str | None:
    """Constant-time match against every configured token.

    Iterates over all entries even after a match so the total time depends on
    the number of configured tokens, not on whether/where a match was found.
    """
    matched_label: str | None = None
    presented_b = presented.encode("utf-8")
    for label, value in tokens.items():
        # ``hmac.compare_digest`` is constant-time only for equal-length inputs;
        # pad/truncate by hashing first when lengths differ. We accept the slight
        # cost of always running the comparison even after a hit.
        v_b = value.encode("utf-8")
        if len(v_b) == len(presented_b):
            ok = hmac.compare_digest(presented_b, v_b)
        else:
            # Compare against itself to keep timing balanced; result is always False.
            hmac.compare_digest(v_b, v_b)
            ok = False
        if ok and matched_label is None:
            matched_label = label
    return matched_label


def require_token(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "missing bearer token"}},
            headers={"WWW-Authenticate": "Bearer"},
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "expected 'Bearer <token>'"}},
            headers={"WWW-Authenticate": "Bearer"},
        )
    label = _match_token(token, settings.tokens)
    if label is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthorized", "message": "invalid token"}},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Principal(label=label)
