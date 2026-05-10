"""Insert rows into ``claude_calls`` for retrieval telemetry.

Per CLAUDE.md "Rate-limit accounting", the bot writes one row per ``claude -p``
invocation with ``service='telegram_bot'``, ``purpose='retrieve'``, and
``queue_item_id=NULL``. The schema is owned by the worker's migrations
(``worker/migrations/001_claude_calls.sql``); the bot is a writer, not an
owner. We open a fresh connection per call so the bot does not have to
manage connection lifecycle alongside the asyncio loop.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .logging import log_event


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def record_claude_call(
    db_path: Path,
    *,
    purpose: str,
    session_id: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    duration_ms: int | None,
    exit_code: int,
    timeout: bool = False,
) -> None:
    """Insert one row into ``claude_calls`` with ``service='telegram_bot'``.

    A failure to insert is logged and swallowed: telemetry must not take down
    the bot.
    """
    if not db_path.exists():
        log_event(
            "claude_call_telemetry_skipped",
            level=logging.WARNING,
            reason="db_missing",
            db_path=str(db_path),
        )
        return
    try:
        conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute(
                "INSERT INTO claude_calls "
                "(ts, service, purpose, queue_item_id, session_id, "
                " input_tokens, output_tokens, duration_ms, exit_code) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    _utc_now_iso(),
                    "telegram_bot",
                    purpose,
                    None,
                    session_id,
                    input_tokens,
                    output_tokens,
                    duration_ms,
                    exit_code,
                ),
            )
        finally:
            conn.close()
    except sqlite3.Error as exc:
        log_event(
            "claude_call_telemetry_failed",
            level=logging.WARNING,
            error_message=str(exc),
            timeout=timeout,
        )
