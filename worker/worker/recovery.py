"""Startup recovery: any rows left in ``processing`` (process crash, OOM, etc.)
must be returned to ``queued`` so they get a fresh attempt."""
from __future__ import annotations

import sqlite3

from worker.db import utc_now_iso
from worker.logging import log_event


def reset_stuck_processing(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "UPDATE queue SET status='queued', updated_at=? WHERE status='processing'",
        (utc_now_iso(),),
    )
    count = int(cur.rowcount)
    log_event("processing_rows_reset", count=count)
    return count
