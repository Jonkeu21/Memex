"""Rate-limit telemetry endpoint.

Reads the ``claude_calls`` table that the worker, telegram_bot, and dashboard
all populate. Returns:

- 24-hour totals,
- per-hour x per-service stacked-bar buckets,
- the rolling 5-minute non-zero-exit-code error rate,
- the most recent 20 calls.

If the ``claude_calls`` table doesn't exist yet (e.g. the worker hasn't
applied its migrations on a fresh deployment), the endpoint returns
``available: false`` with empty arrays so the frontend can show a friendly
"telemetry not yet recorded" empty state instead of a 500.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request

from ..db import table_exists
from ..schemas import (
    CallsByHourBucket,
    ClaudeCallRow,
    RateLimitSnapshot,
)

router = APIRouter(prefix="/api/v1/rate-limit", tags=["rate_limit"])


def _hour_bucket(ts_iso: str) -> str:
    """Parse the ISO timestamp and return the YYYY-MM-DDThh:00:00Z bucket."""
    try:
        cleaned = ts_iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return ts_iso
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    floored = dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return floored.strftime("%Y-%m-%dT%H:%M:%SZ")


def _empty_snapshot(available: bool = False) -> RateLimitSnapshot:
    return RateLimitSnapshot(
        available=available,
        total_24h=0,
        error_rate_5m=0.0,
        last_call_ts=None,
        by_hour=[],
        recent_calls=[],
        services_breakdown_24h={},
    )


@router.get("", response_model=RateLimitSnapshot)
def get_rate_limit(request: Request) -> RateLimitSnapshot:
    conn: sqlite3.Connection = request.app.state.db
    if not table_exists(conn, "claude_calls"):
        return _empty_snapshot(available=False)

    now = datetime.now(timezone.utc)
    horizon_24h = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    horizon_5m = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # 24-hour rows for stacked bars + service breakdown.
    rows = list(
        conn.execute(
            """
            SELECT ts, service, purpose, queue_item_id, session_id,
                   input_tokens, output_tokens, duration_ms, exit_code
              FROM claude_calls
             WHERE ts >= ?
            """,
            (horizon_24h,),
        )
    )
    bucket_map: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"count": 0, "input": 0, "output": 0}
    )
    services_breakdown: dict[str, int] = defaultdict(int)
    for row in rows:
        bucket_key = (_hour_bucket(row["ts"]), row["service"])
        b = bucket_map[bucket_key]
        b["count"] += 1
        b["input"] += int(row["input_tokens"] or 0)
        b["output"] += int(row["output_tokens"] or 0)
        services_breakdown[row["service"]] += 1
    by_hour = [
        CallsByHourBucket(
            hour=hour,
            service=service,  # type: ignore[arg-type]
            count=stats["count"],
            input_tokens=stats["input"],
            output_tokens=stats["output"],
        )
        for (hour, service), stats in sorted(bucket_map.items())
    ]

    # 5-minute error rate.
    rolling_rows = list(
        conn.execute(
            "SELECT exit_code FROM claude_calls WHERE ts >= ?",
            (horizon_5m,),
        )
    )
    if rolling_rows:
        errors = sum(1 for r in rolling_rows if int(r["exit_code"] or 0) != 0)
        error_rate_5m = errors / len(rolling_rows)
    else:
        error_rate_5m = 0.0

    # Last 20 rows for the recent-calls table.
    recent_rows = list(
        conn.execute(
            """
            SELECT id, ts, service, purpose, queue_item_id, session_id,
                   input_tokens, output_tokens, duration_ms, exit_code
              FROM claude_calls
             ORDER BY ts DESC
             LIMIT 20
            """
        )
    )
    recent_calls = [
        ClaudeCallRow(
            id=int(r["id"]),
            ts=r["ts"],
            service=r["service"],  # type: ignore[arg-type]
            purpose=r["purpose"],  # type: ignore[arg-type]
            queue_item_id=r["queue_item_id"],
            session_id=r["session_id"],
            input_tokens=r["input_tokens"],
            output_tokens=r["output_tokens"],
            duration_ms=r["duration_ms"],
            exit_code=int(r["exit_code"]),
        )
        for r in recent_rows
    ]

    return RateLimitSnapshot(
        available=True,
        total_24h=len(rows),
        error_rate_5m=round(error_rate_5m, 4),
        last_call_ts=recent_calls[0].ts if recent_calls else None,
        by_hour=by_hour,
        recent_calls=recent_calls,
        services_breakdown_24h=dict(services_breakdown),
    )
