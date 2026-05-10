"""SQLite connection management and migration runner.

The database is shared between this service (writer of new rows), the worker
(in-flight updates), and the dashboard (reads). WAL mode lets all three
co-exist with the modest contention of a single-user system.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# A single write lock is enough: SQLite already serialises writes, but the
# Python sqlite3 module exposes ``last_insert_rowid()`` on the connection,
# which is per-connection state — concurrent writers on a shared connection
# can race and observe each other's rowids. The lock avoids that and makes
# behaviour identical whether the routes run on the asyncio event loop or
# in FastAPI's sync threadpool.
WRITE_LOCK = threading.Lock()

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


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


def run_migrations(conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every .sql file in lexicographic order, idempotently.

    Returns the list of filenames newly applied this call.
    """
    _ensure_migrations_table(conn)
    applied = {
        row[0] for row in conn.execute("SELECT filename FROM _migrations")
    }
    files = sorted(p for p in migrations_dir.glob("*.sql") if p.is_file())
    newly: list[str] = []
    for path in files:
        if path.name in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        # ``executescript`` commits any open transaction implicitly, so we run
        # it outside our own BEGIN/COMMIT. If the script fails, the migration
        # row is not recorded and the next startup retries (every migration
        # uses ``CREATE TABLE IF NOT EXISTS``-style idempotent DDL).
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO _migrations (filename, applied_at) VALUES (?, datetime('now'))",
            (path.name,),
        )
        newly.append(path.name)
    return newly


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def is_writable(db_path: Path) -> bool:
    try:
        conn = connect(db_path)
    except sqlite3.Error:
        return False
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _readyz_probe (id INTEGER PRIMARY KEY)"
        )
        conn.execute("INSERT INTO _readyz_probe DEFAULT VALUES")
        conn.execute("DELETE FROM _readyz_probe")
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()
