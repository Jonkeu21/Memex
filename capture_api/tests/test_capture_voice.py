from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio


async def test_voice_happy_path(app_and_client, auth_header) -> None:
    app, client = app_and_client
    resp = await client.post(
        "/captures/voice",
        headers=auth_header,
        files={"file": ("voice.ogg", b"OggS....", "audio/ogg")},
    )
    assert resp.status_code == 202
    body = resp.json()
    row = app.state.db.execute(
        "SELECT * FROM queue WHERE id=?", (body["id"],)
    ).fetchone()
    assert row["source_type"] == "voice"
    payload = json.loads(row["source_payload"])
    assert payload["mime_type"] == "audio/ogg"
    assert Path(payload["stored_path"]).exists()


async def test_voice_rejects_non_audio(app_and_client, auth_header) -> None:
    app, client = app_and_client
    resp = await client.post(
        "/captures/voice",
        headers=auth_header,
        files={"file": ("doc.pdf", b"PDF", "application/pdf")},
    )
    assert resp.status_code == 400
    n = app.state.db.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
    assert n == 0
