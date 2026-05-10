from __future__ import annotations

import json
import sqlite3

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_url_capture_happy_path(
    app_and_client, auth_header, settings
) -> None:
    app, client = app_and_client
    resp = await client.post(
        "/captures/url",
        json={"url": "https://example.com/article", "user_note": "skim later"},
        headers=auth_header,
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert isinstance(body["id"], int)
    assert body["created_at"].endswith("Z")

    conn: sqlite3.Connection = app.state.db
    row = conn.execute("SELECT * FROM queue WHERE id=?", (body["id"],)).fetchone()
    assert row["source_type"] == "url"
    assert row["status"] == "queued"
    assert row["submitter"] == "api:test"
    assert json.loads(row["source_payload"]) == {
        "url": "https://example.com/article",
        "user_note": "skim later",
    }


async def test_invalid_url_is_422(client: AsyncClient, auth_header) -> None:
    resp = await client.post(
        "/captures/url", json={"url": "not-a-url"}, headers=auth_header
    )
    assert resp.status_code == 422


async def test_missing_url_is_422(client: AsyncClient, auth_header) -> None:
    resp = await client.post("/captures/url", json={}, headers=auth_header)
    assert resp.status_code == 422


async def test_extra_field_is_rejected(client: AsyncClient, auth_header) -> None:
    resp = await client.post(
        "/captures/url",
        json={"url": "https://example.com/", "extra": 1},
        headers=auth_header,
    )
    assert resp.status_code == 422


async def test_url_default_user_note_blank(
    app_and_client, auth_header
) -> None:
    app, client = app_and_client
    resp = await client.post(
        "/captures/url", json={"url": "https://example.com/"}, headers=auth_header
    )
    assert resp.status_code == 202
    row = app.state.db.execute(
        "SELECT source_payload FROM queue WHERE id=?", (resp.json()["id"],)
    ).fetchone()
    assert json.loads(row["source_payload"])["user_note"] == ""
