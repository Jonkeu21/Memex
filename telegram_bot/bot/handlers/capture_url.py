"""URL capture handler."""
from __future__ import annotations

import logging
from typing import Any

from ..capture_client import CaptureAPIError, CaptureClient
from ..intent import Decision
from ..logging import hash_chat_id, log_event
from ..rendering import acknowledgement


async def handle_capture_url(
    *,
    message: Any,
    decision: Decision,
    client: CaptureClient,
) -> None:
    chat_id = getattr(message.chat, "id", None) if hasattr(message, "chat") else None
    url = decision.url or ""
    user_note = decision.user_note
    try:
        ack = await client.capture_url(url, user_note=user_note)
    except CaptureAPIError as exc:
        log_event(
            "capture_failed",
            level=logging.ERROR,
            intent="capture_url",
            submitter_hash=hash_chat_id(chat_id if chat_id is not None else "unknown"),
            status_code=exc.status_code,
            error_message=str(exc),
        )
        await message.reply_text(
            "Sorry — the capture API rejected that. Try again in a moment.",
            reply_to_message_id=getattr(message, "message_id", None),
        )
        return
    log_event(
        "capture_acknowledged",
        intent="capture_url",
        queue_item_id=ack.id,
        submitter_hash=hash_chat_id(chat_id if chat_id is not None else "unknown"),
    )
    await message.reply_text(
        acknowledgement(ack.id, "url"),
        reply_to_message_id=getattr(message, "message_id", None),
    )
