"""Command handlers: /start /help /queue /last /find /capture."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from bot.handlers import commands
from tests.conftest import FakeMessage, make_envelope, make_runner


def _seed_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.executescript(
        """
        CREATE TABLE queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_payload TEXT NOT NULL,
            submitter TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            processed_at TEXT,
            confidence REAL,
            vault_path TEXT,
            claude_session_id TEXT,
            claude_input_tokens INTEGER,
            claude_output_tokens INTEGER,
            claude_duration_ms INTEGER
        );
        """
    )
    rows = [
        ("2026-05-10T10:00:00.000000Z", "queued", "url", "/captures/url", None),
        ("2026-05-10T11:00:00.000000Z", "filed", "text", "/captures/text", "areas/x.md"),
        ("2026-05-10T12:00:00.000000Z", "needs_review", "voice", "/captures/voice", "_inbox/y.md"),
        ("2026-05-10T13:00:00.000000Z", "filed", "url", "/captures/url", "resources/z.md"),
    ]
    for created, status, src_type, payload, vault_path in rows:
        conn.execute(
            "INSERT INTO queue (created_at, updated_at, source_type, source_payload, submitter, status, vault_path) "
            "VALUES (?, ?, ?, ?, 'api:telegram', ?, ?)",
            (created, created, src_type, payload, status, vault_path),
        )
    conn.close()


@pytest.mark.asyncio
async def test_cmd_start_greets():
    msg = FakeMessage(text="/start")
    await commands.cmd_start(msg)
    assert "Memex" in msg.replies[0].text
    assert "/queue" in msg.replies[0].text
    assert "/find" in msg.replies[0].text
    assert "/capture" in msg.replies[0].text


@pytest.mark.asyncio
async def test_cmd_help_same_as_start():
    msg = FakeMessage(text="/help")
    await commands.cmd_help(msg)
    assert "/queue" in msg.replies[0].text


@pytest.mark.asyncio
async def test_cmd_queue_renders_counts(settings):
    _seed_db(settings.db_path)
    msg = FakeMessage(text="/queue")
    await commands.cmd_queue(msg, settings=settings)
    body = msg.replies[0].text
    assert "queued: 1" in body
    assert "filed: 2" in body
    assert "needs_review: 1" in body
    assert "failed: 0" in body


@pytest.mark.asyncio
async def test_cmd_queue_unavailable_when_no_db(settings):
    msg = FakeMessage(text="/queue")
    await commands.cmd_queue(msg, settings=settings)
    assert "unavailable" in msg.replies[0].text


@pytest.mark.asyncio
async def test_cmd_last_renders_recent(settings):
    _seed_db(settings.db_path)
    msg = FakeMessage(text="/last")
    await commands.cmd_last(msg, settings=settings)
    body = msg.replies[0].text
    assert "Most recent" in body
    assert "resources/z.md" in body
    assert "_inbox/y.md" in body


@pytest.mark.asyncio
async def test_cmd_last_empty(tmp_path, settings):
    _seed_db(settings.db_path)
    # Drop rows.
    conn = sqlite3.connect(settings.db_path, isolation_level=None)
    conn.execute("DELETE FROM queue")
    conn.close()
    msg = FakeMessage(text="/last")
    await commands.cmd_last(msg, settings=settings)
    assert "No captures yet" in msg.replies[0].text


@pytest.mark.asyncio
async def test_cmd_last_unavailable_when_no_db(settings):
    msg = FakeMessage(text="/last")
    await commands.cmd_last(msg, settings=settings)
    assert "unavailable" in msg.replies[0].text


@pytest.mark.asyncio
async def test_cmd_find_invokes_retrieval(settings):
    inner = {"answer": "ok", "sources": [], "quotes": [], "confidence": 0.5}
    runner = make_runner(stdout=make_envelope(inner))
    msg = FakeMessage(text="/find what about sleep")
    await commands.cmd_find(
        msg,
        settings=settings,
        prompt_template="q={question}",
        runner=runner,
    )
    # Retrieval renders an answer reply.
    assert any("ok" in r.text for r in msg.replies)


@pytest.mark.asyncio
async def test_cmd_find_requires_query(settings):
    msg = FakeMessage(text="/find")
    await commands.cmd_find(
        msg,
        settings=settings,
        prompt_template="q={question}",
        runner=make_runner(stdout=""),
    )
    assert "Usage" in msg.replies[0].text


@pytest.mark.asyncio
async def test_cmd_capture_forces_text_intent(client, mock_api):
    msg = FakeMessage(text="/capture this is the body to save")
    await commands.cmd_capture(msg, client=client)
    assert mock_api.requests[0].url.path == "/captures/text"
    import json
    payload = json.loads(mock_api.requests[0].content)
    assert payload == {"text": "this is the body to save"}


@pytest.mark.asyncio
async def test_cmd_capture_requires_body(client, mock_api):
    msg = FakeMessage(text="/capture")
    await commands.cmd_capture(msg, client=client)
    assert mock_api.requests == []
    assert "Usage" in msg.replies[0].text
