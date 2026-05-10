from __future__ import annotations

import inspect

import pytest
from httpx import AsyncClient

from app import auth as auth_mod


pytestmark = pytest.mark.asyncio


async def test_missing_header_is_401(client: AsyncClient) -> None:
    resp = await client.post("/captures/text", json={"text": "hi"})
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


async def test_wrong_scheme_is_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/captures/text", json={"text": "hi"}, headers={"Authorization": "Basic xyz"}
    )
    assert resp.status_code == 401


async def test_wrong_token_is_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/captures/text", json={"text": "hi"}, headers={"Authorization": "Bearer nope"}
    )
    assert resp.status_code == 401


async def test_correct_token_is_202(client: AsyncClient, auth_header) -> None:
    resp = await client.post("/captures/text", json={"text": "hi"}, headers=auth_header)
    assert resp.status_code == 202


async def test_constant_time_compare_in_use() -> None:
    """Source-level assertion that the auth helper uses ``hmac.compare_digest``."""
    src = inspect.getsource(auth_mod._match_token)
    assert "hmac.compare_digest" in src


async def test_readyz_requires_auth(client: AsyncClient, auth_header) -> None:
    assert (await client.get("/readyz")).status_code == 401
    ok = await client.get("/readyz", headers=auth_header)
    assert ok.status_code == 200
    assert ok.json() == {"status": "ok"}


async def test_healthz_no_auth(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
