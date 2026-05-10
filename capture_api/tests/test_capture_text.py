from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_text_capture_happy_path(app_and_client, auth_header) -> None:
    app, client = app_and_client
    resp = await client.post(
        "/captures/text", json={"text": "hello world"}, headers=auth_header
    )
    assert resp.status_code == 202
    body = resp.json()
    row = app.state.db.execute(
        "SELECT * FROM queue WHERE id=?", (body["id"],)
    ).fetchone()
    assert row["source_type"] == "text"
    assert json.loads(row["source_payload"]) == {"text": "hello world"}


async def test_empty_text_is_422(client: AsyncClient, auth_header) -> None:
    resp = await client.post("/captures/text", json={"text": ""}, headers=auth_header)
    assert resp.status_code == 422


async def test_blank_text_is_422(client: AsyncClient, auth_header) -> None:
    resp = await client.post(
        "/captures/text", json={"text": "   "}, headers=auth_header
    )
    assert resp.status_code == 422


async def test_text_too_long(client: AsyncClient, auth_header) -> None:
    resp = await client.post(
        "/captures/text", json={"text": "x" * 100_001}, headers=auth_header
    )
    assert resp.status_code == 422


async def test_text_missing_field_is_422(client: AsyncClient, auth_header) -> None:
    resp = await client.post("/captures/text", json={}, headers=auth_header)
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body  # FastAPI standard envelope
