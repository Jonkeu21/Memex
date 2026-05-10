"""Read-only SQLite queries for /queue and /last.

The Telegram bot is the only component besides the dashboard that needs to
read the queue without mutating it. We open a fresh connection per call,
``mode=ro``, so the bot can never accidentally write — see CLAUDE.md
"Worker contract" / "Capture API surface" for who is allowed to write.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass
class StatusCounts:
    queued: int = 0
    processing: int = 0
    filed: int = 0
    needs_review: int = 0
    failed: int = 0


@dataclass
class RecentItem:
    id: int
    status: str
    source_type: str
    created_at: str
    vault_path: str | None


class QueueUnavailable(RuntimeError):
    """Raised when the SQLite file cannot be opened read-only."""


def _connect_ro(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise QueueUnavailable(f"queue db missing at {db_path}")
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    except sqlite3.OperationalError as exc:
        raise QueueUnavailable(str(exc)) from exc
    conn.row_factory = sqlite3.Row
    return conn


def status_counts_24h(db_path: Path, *, now: datetime | None = None) -> StatusCounts:
    """Return counts grouped by status for rows created in the last 24 hours."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=24)
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    conn = _connect_ro(db_path)
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM queue WHERE created_at >= ? GROUP BY status",
            (cutoff_iso,),
        ).fetchall()
    finally:
        conn.close()
    counts = StatusCounts()
    for row in rows:
        setattr(counts, row["status"], int(row["n"]))
    return counts


def recent_items(db_path: Path, limit: int = 5) -> list[RecentItem]:
    conn = _connect_ro(db_path)
    try:
        rows = conn.execute(
            "SELECT id, status, source_type, created_at, vault_path "
            "FROM queue ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [
        RecentItem(
            id=int(row["id"]),
            status=str(row["status"]),
            source_type=str(row["source_type"]),
            created_at=str(row["created_at"]),
            vault_path=row["vault_path"],
        )
        for row in rows
    ]
