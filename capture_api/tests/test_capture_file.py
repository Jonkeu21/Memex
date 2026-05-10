from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio


async def test_file_capture_happy_path(app_and_client, auth_header, settings) -> None:
    app, client = app_and_client
    resp = await client.post(
        "/captures/file",
        headers=auth_header,
        files={"file": ("scan.pdf", b"PDF body bytes", "application/pdf")},
    )
    assert resp.status_code == 202
    body = resp.json()
    row = app.state.db.execute(
        "SELECT * FROM queue WHERE id=?", (body["id"],)
    ).fetchone()
    assert row["source_type"] == "file"
    payload = json.loads(row["source_payload"])
    stored = Path(payload["stored_path"])
    assert stored.exists()
    assert stored.read_bytes() == b"PDF body bytes"
    assert payload["mime_type"] == "application/pdf"
    assert payload["original_filename"] == "scan.pdf"
    assert payload["size_bytes"] == len(b"PDF body bytes")
    # Path layout: <inbox>/YYYY/MM/DD/<uuid>__<name>
    relative = stored.relative_to(settings.inbox_dir)
    assert len(relative.parts) == 4
    assert relative.parts[-1].endswith("__scan.pdf")


async def test_file_oversize_returns_413(app_and_client, auth_header, settings) -> None:
    app, client = app_and_client
    payload = b"x" * (settings.max_upload_bytes + 1)
    resp = await client.post(
        "/captures/file",
        headers=auth_header,
        files={"file": ("big.bin", payload, "application/octet-stream")},
    )
    assert resp.status_code == 413
    # No row written.
    n = app.state.db.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
    assert n == 0
    # No file written under the inbox.
    leftover = list(settings.inbox_dir.rglob("*"))
    files = [p for p in leftover if p.is_file()]
    assert files == []


async def test_filename_with_path_traversal_is_rejected(
    app_and_client, auth_header, settings
) -> None:
    app, client = app_and_client
    resp = await client.post(
        "/captures/file",
        headers=auth_header,
        files={"file": ("../../etc/passwd", b"evil", "application/octet-stream")},
    )
    assert resp.status_code == 400
    n = app.state.db.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
    assert n == 0
    leftover = [p for p in settings.inbox_dir.rglob("*") if p.is_file()]
    assert leftover == []


async def test_filename_with_separator_is_sanitised_to_basename(
    app_and_client, auth_header, settings
) -> None:
    app, client = app_and_client
    resp = await client.post(
        "/captures/file",
        headers=auth_header,
        files={"file": ("subdir/clean.pdf", b"ok", "application/pdf")},
    )
    assert resp.status_code == 202
    row = app.state.db.execute(
        "SELECT source_payload FROM queue WHERE id=?", (resp.json()["id"],)
    ).fetchone()
    payload = json.loads(row["source_payload"])
    assert payload["original_filename"] == "clean.pdf"
    assert "/" not in payload["original_filename"]


async def test_missing_file_field_is_422(client, auth_header) -> None:
    resp = await client.post("/captures/file", headers=auth_header)
    assert resp.status_code == 422
