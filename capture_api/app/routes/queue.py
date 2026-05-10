"""Read-only queue introspection: GET /captures and GET /captures/{id}."""
from __future__ import annotations

import json
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..auth import Principal, require_token
from ..schemas import QueueItem, QueueListing, SourceType, QueueStatus

router = APIRouter()


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
    payload: Any
    raw = row["source_payload"]
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {"_raw": raw}
    data = {col: row[col] for col in _QUEUE_COLUMNS}
    data["source_payload"] = payload
    return QueueItem(**data)


@router.get("/captures", response_model=QueueListing)
def list_captures(
    request: Request,
    _: Annotated[Principal, Depends(require_token)],
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


@router.get("/captures/{item_id}", response_model=QueueItem)
def get_capture(
    item_id: int,
    request: Request,
    _: Annotated[Principal, Depends(require_token)],
) -> QueueItem:
    conn: sqlite3.Connection = request.app.state.db
    row = conn.execute(
        f"SELECT {', '.join(_QUEUE_COLUMNS)} FROM queue WHERE id = ?",
        (item_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {"code": "not_found", "message": f"no queue item with id {item_id}"}
            },
        )
    return _row_to_item(row)
