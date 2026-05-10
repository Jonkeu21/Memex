"""Queue inspection + operator actions (retry, cancel)."""
from __future__ import annotations

import json
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..auth import require_token
from ..db import utc_now_iso
from ..logging import log_event
from ..schemas import (
    QueueActionAck,
    QueueItem,
    QueueListing,
    QueueStatus,
    SourceType,
)

router = APIRouter(prefix="/api/v1/queue", tags=["queue"])


_QUEUE_COLUMNS = (
    "id",
    "created_at",
    "updated_at",
    "source_type",
    "source_payload",
    "submitter",
    "status",
    "attempts",
    "last_error",
    "processed_at",
    "confidence",
    "vault_path",
    "claude_session_id",
    "claude_input_tokens",
    "claude_output_tokens",
    "claude_duration_ms",
)


def _row_to_item(row: sqlite3.Row) -> QueueItem:
    raw = row["source_payload"]
    try:
        payload: Any = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {"_raw": raw}
    data = {col: row[col] for col in _QUEUE_COLUMNS}
    data["source_payload"] = payload
    return QueueItem(**data)


def _get_row(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return conn.execute(
        f"SELECT {', '.join(_QUEUE_COLUMNS)} FROM queue WHERE id = ?",
        (item_id,),
    ).fetchone()


def _not_found(item_id: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": {
                "code": "not_found",
                "message": f"no queue item with id {item_id}",
            }
        },
    )


@router.get("", response_model=QueueListing)
def list_queue(
    request: Request,
    status_filter: Annotated[QueueStatus | None, Query(alias="status")] = None,
    source_type: Annotated[SourceType | None, Query()] = None,
    cursor: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> QueueListing:
    conn: sqlite3.Connection = request.app.state.db
    where: list[str] = []
    params: list[Any] = []
    if status_filter is not None:
        where.append("status = ?")
        params.append(status_filter)
    if source_type is not None:
        where.append("source_type = ?")
        params.append(source_type)
    if cursor is not None:
        where.append("id < ?")
        params.append(cursor)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = (
        f"SELECT {', '.join(_QUEUE_COLUMNS)} FROM queue {where_sql} "
        f"ORDER BY id DESC LIMIT ?"
    )
    rows = list(conn.execute(sql, (*params, limit + 1)))
    next_cursor: int | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = rows[-1]["id"]
    return QueueListing(items=[_row_to_item(r) for r in rows], next_cursor=next_cursor)


@router.get("/{item_id}", response_model=QueueItem)
def get_queue_item(item_id: int, request: Request) -> QueueItem:
    conn: sqlite3.Connection = request.app.state.db
    row = _get_row(conn, item_id)
    if row is None:
        raise _not_found(item_id)
    return _row_to_item(row)


@router.post(
    "/{item_id}/retry",
    response_model=QueueActionAck,
    dependencies=[Depends(require_token)],
)
def retry_queue_item(item_id: int, request: Request) -> QueueActionAck:
    conn: sqlite3.Connection = request.app.state.db
    row = _get_row(conn, item_id)
    if row is None:
        raise _not_found(item_id)
    if row["status"] not in {"failed", "needs_review"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "invalid_status",
                    "message": (
                        f"cannot retry item in status {row['status']!r}; "
                        "only 'failed' or 'needs_review' items may be retried"
                    ),
                }
            },
        )
    conn.execute(
        "UPDATE queue SET status='queued', updated_at=?, last_error=NULL WHERE id=?",
        (utc_now_iso(), item_id),
    )
    log_event(
        "queue_retry_requested",
        queue_item_id=item_id,
        previous_status=row["status"],
    )
    return QueueActionAck(id=item_id, status="queued")


@router.post(
    "/{item_id}/cancel",
    response_model=QueueActionAck,
    dependencies=[Depends(require_token)],
)
def cancel_queue_item(item_id: int, request: Request) -> QueueActionAck:
    conn: sqlite3.Connection = request.app.state.db
    row = _get_row(conn, item_id)
    if row is None:
        raise _not_found(item_id)
    if row["status"] not in {"queued", "needs_review"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "invalid_status",
                    "message": (
                        f"cannot cancel item in status {row['status']!r}; "
                        "only 'queued' or 'needs_review' items may be cancelled"
                    ),
                }
            },
        )
    now = utc_now_iso()
    conn.execute(
        "UPDATE queue SET status='failed', updated_at=?, processed_at=?, "
        "last_error=? WHERE id=?",
        (now, now, "cancelled by operator via dashboard", item_id),
    )
    log_event(
        "queue_cancelled",
        queue_item_id=item_id,
        previous_status=row["status"],
    )
    return QueueActionAck(id=item_id, status="failed")
