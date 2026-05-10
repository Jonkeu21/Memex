"""SQLite connection helpers, queue transitions, and claude_calls telemetry.

The worker is the only writer of statuses other than ``queued``. Every state
transition here is encoded as one named function so callers cannot accidentally
write a free-form UPDATE.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass
class ClaudeTelemetry:
    session_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        db_path,
        isolation_level=None,
        check_same_thread=False,
        timeout=30.0,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _migrations (
            filename   TEXT    PRIMARY KEY,
            applied_at TEXT    NOT NULL
        )
        """
    )


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> list[str]:
    _ensure_migrations_table(conn)
    applied = {row[0] for row in conn.execute("SELECT filename FROM _migrations")}
    files = sorted(p for p in migrations_dir.glob("*.sql") if p.is_file())
    newly: list[str] = []
    for path in files:
        if path.name in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO _migrations (filename, applied_at) VALUES (?, ?)",
            (path.name, utc_now_iso()),
        )
        newly.append(path.name)
    return newly


def claim_batch(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    """Atomically move up to ``limit`` queued rows into ``processing``.

    Each candidate row is claimed individually with a status-guarded UPDATE so
    a parallel worker (or a manual UPDATE in transit) loses without harming
    the loop. Returns the freshly-fetched rows in oldest-first order.
    """
    candidates = list(
        conn.execute(
            "SELECT id FROM queue WHERE status = 'queued' ORDER BY created_at ASC LIMIT ?",
            (limit,),
        )
    )
    claimed_ids: list[int] = []
    now = utc_now_iso()
    for row in candidates:
        cur = conn.execute(
            "UPDATE queue "
            "SET status='processing', updated_at=?, attempts=attempts+1 "
            "WHERE id=? AND status='queued'",
            (now, row["id"]),
        )
        if cur.rowcount == 1:
            claimed_ids.append(row["id"])
    if not claimed_ids:
        return []
    placeholders = ",".join("?" for _ in claimed_ids)
    rows = list(
        conn.execute(
            f"SELECT * FROM queue WHERE id IN ({placeholders}) ORDER BY created_at ASC",
            claimed_ids,
        )
    )
    return rows


def _update_terminal(
    conn: sqlite3.Connection,
    *,
    queue_item_id: int,
    status: str,
    confidence: float | None,
    vault_path: str | None,
    telemetry: ClaudeTelemetry | None,
    last_error: str | None,
) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE queue
           SET status = ?,
               updated_at = ?,
               processed_at = ?,
               confidence = ?,
               vault_path = ?,
               claude_session_id = ?,
               claude_input_tokens = ?,
               claude_output_tokens = ?,
               claude_duration_ms = ?,
               last_error = ?
         WHERE id = ?
        """,
        (
            status,
            now,
            now,
            confidence,
            vault_path,
            telemetry.session_id if telemetry else None,
            telemetry.input_tokens if telemetry else None,
            telemetry.output_tokens if telemetry else None,
            telemetry.duration_ms if telemetry else None,
            last_error,
            queue_item_id,
        ),
    )


def mark_filed(
    conn: sqlite3.Connection,
    queue_item_id: int,
    vault_path: str,
    confidence: float,
    telemetry: ClaudeTelemetry,
) -> None:
    _update_terminal(
        conn,
        queue_item_id=queue_item_id,
        status="filed",
        confidence=confidence,
        vault_path=vault_path,
        telemetry=telemetry,
        last_error=None,
    )


def mark_needs_review(
    conn: sqlite3.Connection,
    queue_item_id: int,
    vault_path: str,
    confidence: float | None,
    telemetry: ClaudeTelemetry | None,
    last_error: str | None = None,
) -> None:
    _update_terminal(
        conn,
        queue_item_id=queue_item_id,
        status="needs_review",
        confidence=confidence,
        vault_path=vault_path,
        telemetry=telemetry,
        last_error=last_error,
    )


def mark_failed(
    conn: sqlite3.Connection,
    queue_item_id: int,
    last_error: str,
    telemetry: ClaudeTelemetry | None = None,
) -> None:
    _update_terminal(
        conn,
        queue_item_id=queue_item_id,
        status="failed",
        confidence=None,
        vault_path=None,
        telemetry=telemetry,
        last_error=last_error,
    )


def release_for_retry(
    conn: sqlite3.Connection,
    queue_item_id: int,
    last_error: str,
) -> None:
    conn.execute(
        "UPDATE queue SET status='queued', updated_at=?, last_error=? WHERE id=?",
        (utc_now_iso(), last_error, queue_item_id),
    )


def record_claude_call(
    conn: sqlite3.Connection,
    *,
    ts: str,
    service: str,
    purpose: str,
    queue_item_id: int | None,
    session_id: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    duration_ms: int | None,
    exit_code: int,
) -> None:
    conn.execute(
        """
        INSERT INTO claude_calls
            (ts, service, purpose, queue_item_id, session_id,
             input_tokens, output_tokens, duration_ms, exit_code)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts,
            service,
            purpose,
            queue_item_id,
            session_id,
            input_tokens,
            output_tokens,
            duration_ms,
            exit_code,
        ),
    )


def get_attempts(conn: sqlite3.Connection, queue_item_id: int) -> int:
    row = conn.execute(
        "SELECT attempts FROM queue WHERE id=?", (queue_item_id,)
    ).fetchone()
    return int(row["attempts"]) if row else 0


def install_queue_schema(conn: sqlite3.Connection) -> None:
    """Used by tests when constructing an in-memory queue without capture_api."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS queue (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at      TEXT    NOT NULL,
            updated_at      TEXT    NOT NULL,
            source_type     TEXT    NOT NULL CHECK (source_type IN ('url','file','text','voice')),
            source_payload  TEXT    NOT NULL,
            submitter       TEXT    NOT NULL,
            status          TEXT    NOT NULL DEFAULT 'queued'
                            CHECK (status IN ('queued','processing','filed','needs_review','failed')),
            attempts        INTEGER NOT NULL DEFAULT 0,
            last_error      TEXT,
            processed_at    TEXT,
            confidence      REAL,
            vault_path      TEXT,
            claude_session_id TEXT,
            claude_input_tokens  INTEGER,
            claude_output_tokens INTEGER,
            claude_duration_ms   INTEGER
        );
        CREATE INDEX IF NOT EXISTS queue_status_created_at ON queue (status, created_at);
        CREATE INDEX IF NOT EXISTS queue_submitter         ON queue (submitter);
        """
    )


def insert_queue_row(
    conn: sqlite3.Connection,
    *,
    source_type: str,
    source_payload: str,
    submitter: str,
    created_at: str | None = None,
) -> int:
    """Test-helper: emulate what the capture API writes."""
    ts = created_at or utc_now_iso()
    cur = conn.execute(
        "INSERT INTO queue (created_at, updated_at, source_type, source_payload, submitter, status) "
        "VALUES (?, ?, ?, ?, ?, 'queued')",
        (ts, ts, source_type, source_payload, submitter),
    )
    return int(cur.lastrowid)
