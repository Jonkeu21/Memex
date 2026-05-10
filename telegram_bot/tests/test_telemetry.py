"""claude_calls telemetry insertion."""
from __future__ import annotations

import sqlite3

from bot.telemetry import record_claude_call


def _seed_claude_calls_schema(db_path):
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.executescript(
        """
        CREATE TABLE claude_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            service TEXT NOT NULL,
            purpose TEXT NOT NULL,
            queue_item_id INTEGER,
            session_id TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            duration_ms INTEGER,
            exit_code INTEGER NOT NULL
        );
        """
    )
    conn.close()


def test_record_claude_call_inserts_row(tmp_path):
    db = tmp_path / "memex.db"
    _seed_claude_calls_schema(db)
    record_claude_call(
        db,
        purpose="retrieve",
        session_id="sess-1",
        input_tokens=100,
        output_tokens=20,
        duration_ms=1500,
        exit_code=0,
    )
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT service, purpose, queue_item_id, session_id, exit_code FROM claude_calls").fetchall()
    conn.close()
    assert rows == [("telegram_bot", "retrieve", None, "sess-1", 0)]


def test_record_claude_call_skipped_when_db_missing(tmp_path):
    # Should not raise; logs a warning and returns silently.
    record_claude_call(
        tmp_path / "no_such_db.sqlite",
        purpose="retrieve",
        session_id=None,
        input_tokens=None,
        output_tokens=None,
        duration_ms=None,
        exit_code=-1,
    )


def test_record_claude_call_swallows_sqlite_error(tmp_path):
    # DB exists but no claude_calls table → sqlite3.OperationalError caught.
    db = tmp_path / "memex.db"
    sqlite3.connect(db).close()
    record_claude_call(
        db,
        purpose="retrieve",
        session_id=None,
        input_tokens=None,
        output_tokens=None,
        duration_ms=10,
        exit_code=0,
    )
