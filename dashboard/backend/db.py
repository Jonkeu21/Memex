"""SQLite connection helpers for the dashboard backend.

The dashboard reads the queue + claude_calls (telemetry) and writes to the
queue when the operator retries / cancels items. WAL mode is on so the
worker, capture API, and dashboard can all open the same file concurrently.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a read-write connection to the shared SQLite file.

    The dashboard does not own any migrations — capture_api creates ``queue``
    and the worker creates ``claude_calls``. We only check that we can open
    the file; if it doesn't exist yet, the parent directory is created so
    docker bind-mount semantics don't surprise the operator.
    """
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


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None
