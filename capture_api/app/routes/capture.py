"""Capture endpoints — the only writers of new queue rows."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)

from ..auth import Principal, get_settings, require_token
from ..config import Settings
from ..db import WRITE_LOCK
from ..files import StoredUpload, UploadTooLargeError, stream_to_temp
from ..logging import log_event
from ..schemas import CaptureAck, TextCapture, UrlCapture

router = APIRouter()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _insert(
    conn: sqlite3.Connection,
    *,
    source_type: str,
    payload: dict[str, Any],
    submitter: str,
) -> tuple[int, str]:
    now = _utc_now_iso()
    with WRITE_LOCK:
        row = conn.execute(
            """
            INSERT INTO queue (created_at, updated_at, source_type, source_payload,
                               submitter, status, attempts)
            VALUES (?, ?, ?, ?, ?, 'queued', 0)
            RETURNING id
            """,
            (now, now, source_type, json.dumps(payload, separators=(",", ":")), submitter),
        ).fetchone()
    return int(row[0]), now


def _audio_mime(content_type: str | None) -> bool:
    return bool(content_type) and content_type.lower().startswith("audio/")


def _ack(item_id: int, created_at: str) -> CaptureAck:
    return CaptureAck(id=item_id, status="queued", created_at=created_at)


@router.post(
    "/captures/url",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CaptureAck,
)
def capture_url(
    body: UrlCapture,
    request: Request,
    principal: Annotated[Principal, Depends(require_token)],
) -> CaptureAck:
    conn: sqlite3.Connection = request.app.state.db
    payload = {"url": str(body.url), "user_note": body.user_note or ""}
    item_id, created_at = _insert(
        conn, source_type="url", payload=payload, submitter=principal.submitter
    )
    request.state.queue_item_id = item_id
    log_event(
        "capture_received",
        queue_item_id=item_id,
        source_type="url",
        submitter=principal.submitter,
    )
    return _ack(item_id, created_at)


@router.post(
    "/captures/text",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CaptureAck,
)
def capture_text(
    body: TextCapture,
    request: Request,
    principal: Annotated[Principal, Depends(require_token)],
) -> CaptureAck:
    conn: sqlite3.Connection = request.app.state.db
    payload = {"text": body.text}
    item_id, created_at = _insert(
        conn, source_type="text", payload=payload, submitter=principal.submitter
    )
    request.state.queue_item_id = item_id
    log_event(
        "capture_received",
        queue_item_id=item_id,
        source_type="text",
        submitter=principal.submitter,
        source_payload_size_bytes=len(body.text.encode("utf-8")),
    )
    return _ack(item_id, created_at)


def _store_and_enqueue(
    *,
    request: Request,
    conn: sqlite3.Connection,
    settings: Settings,
    upload: UploadFile,
    source_type: str,
    submitter: str,
) -> CaptureAck:
    try:
        stored: StoredUpload = stream_to_temp(
            upload.file,
            inbox_dir=settings.inbox_dir,
            original_filename=upload.filename,
            mime_type=upload.content_type,
            max_bytes=settings.max_upload_bytes,
        )
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail={
                "error": {
                    "code": "payload_too_large",
                    "message": f"upload exceeds {settings.max_upload_mb} MB",
                }
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_payload", "message": str(exc)}},
        ) from exc

    payload: dict[str, Any] = {
        "original_filename": stored.original_filename,
        "stored_path": str(stored.final_path),
        "mime_type": stored.mime_type,
        "size_bytes": stored.size_bytes,
    }
    try:
        item_id, created_at = _insert(
            conn, source_type=source_type, payload=payload, submitter=submitter
        )
        stored.commit()
        request.state.queue_item_id = item_id
    except Exception:
        stored.discard()
        raise

    log_event(
        "capture_received",
        queue_item_id=item_id,
        source_type=source_type,
        submitter=submitter,
        source_payload_size_bytes=stored.size_bytes,
    )
    return _ack(item_id, created_at)


@router.post(
    "/captures/file",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CaptureAck,
)
def capture_file(
    request: Request,
    principal: Annotated[Principal, Depends(require_token)],
    settings: Annotated[Settings, Depends(get_settings)],
    file: UploadFile = File(...),
) -> CaptureAck:
    conn: sqlite3.Connection = request.app.state.db
    return _store_and_enqueue(
        request=request,
        conn=conn,
        settings=settings,
        upload=file,
        source_type="file",
        submitter=principal.submitter,
    )


@router.post(
    "/captures/voice",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CaptureAck,
)
def capture_voice(
    request: Request,
    principal: Annotated[Principal, Depends(require_token)],
    settings: Annotated[Settings, Depends(get_settings)],
    file: UploadFile = File(...),
) -> CaptureAck:
    if not _audio_mime(file.content_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "invalid_payload",
                    "message": "voice uploads must have audio/* content-type",
                }
            },
        )
    conn: sqlite3.Connection = request.app.state.db
    return _store_and_enqueue(
        request=request,
        conn=conn,
        settings=settings,
        upload=file,
        source_type="voice",
        submitter=principal.submitter,
    )
