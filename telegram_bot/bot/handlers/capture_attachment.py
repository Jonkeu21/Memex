"""Attachment capture: voice / audio / document / video / photo.

Per CLAUDE.md, the bot decides between ``/captures/voice`` and ``/captures/file``
by attachment kind:
- voice  → /captures/voice  (Telegram voice messages, audio/ogg)
- audio  → /captures/voice  (audio files, the worker transcribes both)
- video  → /captures/file
- document → /captures/file
- photo → /captures/file (largest size; saved as ``photo_<msg_id>.jpg``)

Files are downloaded into memory and forwarded as multipart. Size is capped
at ``Settings.max_download_bytes``.
"""
from __future__ import annotations

import logging
from typing import Any

from ..capture_client import CaptureAPIError, CaptureAck, CaptureClient
from ..config import Settings
from ..downloads import DownloadError, download_telegram_file
from ..logging import hash_chat_id, log_event
from ..rendering import acknowledgement


def _voice_metadata(message: Any) -> tuple[str, str, str, int | None] | None:
    voice = getattr(message, "voice", None)
    if voice:
        file_id = getattr(voice, "file_id", None)
        size = getattr(voice, "file_size", None)
        mime = getattr(voice, "mime_type", None) or "audio/ogg"
        if file_id:
            return file_id, f"voice_{getattr(message, 'message_id', 'x')}.ogg", mime, size
    audio = getattr(message, "audio", None)
    if audio:
        file_id = getattr(audio, "file_id", None)
        size = getattr(audio, "file_size", None)
        mime = getattr(audio, "mime_type", None) or "audio/mpeg"
        filename = getattr(audio, "file_name", None) or f"audio_{getattr(message, 'message_id', 'x')}"
        if file_id:
            return file_id, filename, mime, size
    return None


def _file_metadata(message: Any) -> tuple[str, str, str, int | None] | None:
    document = getattr(message, "document", None)
    if document:
        file_id = getattr(document, "file_id", None)
        size = getattr(document, "file_size", None)
        mime = getattr(document, "mime_type", None) or "application/octet-stream"
        filename = getattr(document, "file_name", None) or f"document_{getattr(message, 'message_id', 'x')}"
        if file_id:
            return file_id, filename, mime, size
    video = getattr(message, "video", None)
    if video:
        file_id = getattr(video, "file_id", None)
        size = getattr(video, "file_size", None)
        mime = getattr(video, "mime_type", None) or "video/mp4"
        filename = getattr(video, "file_name", None) or f"video_{getattr(message, 'message_id', 'x')}.mp4"
        if file_id:
            return file_id, filename, mime, size
    photos = getattr(message, "photo", None) or []
    if photos:
        # PhotoSize list ascends in width/height. Pick the largest by file_size,
        # falling back to the last entry.
        largest = max(photos, key=lambda p: getattr(p, "file_size", 0) or 0)
        file_id = getattr(largest, "file_id", None)
        size = getattr(largest, "file_size", None)
        if file_id:
            return file_id, f"photo_{getattr(message, 'message_id', 'x')}.jpg", "image/jpeg", size
    return None


async def handle_capture_attachment(
    *,
    message: Any,
    settings: Settings,
    client: CaptureClient,
) -> None:
    chat_id = getattr(message.chat, "id", None) if hasattr(message, "chat") else None
    submitter_hash = hash_chat_id(chat_id if chat_id is not None else "unknown")

    voice_meta = _voice_metadata(message)
    if voice_meta:
        file_id, filename, mime, size = voice_meta
        intent = "capture_voice"
    else:
        file_meta = _file_metadata(message)
        if not file_meta:
            log_event(
                "capture_failed",
                level=logging.WARNING,
                intent="capture_attachment",
                submitter_hash=submitter_hash,
                error_message="no recognised attachment on message",
            )
            await message.reply_text(
                "I couldn't find an attachment in that message.",
                reply_to_message_id=getattr(message, "message_id", None),
            )
            return
        file_id, filename, mime, size = file_meta
        intent = "capture_file"

    try:
        downloaded = await download_telegram_file(
            bot=getattr(message, "_bot", None) or message.get_bot(),
            file_id=file_id,
            filename=filename,
            mime_type=mime,
            max_bytes=settings.max_download_bytes,
            declared_size=size,
        )
    except DownloadError as exc:
        log_event(
            "capture_failed",
            level=logging.WARNING,
            intent=intent,
            submitter_hash=submitter_hash,
            error_message=str(exc),
        )
        await message.reply_text(
            f"Sorry — couldn't accept that file ({exc}).",
            reply_to_message_id=getattr(message, "message_id", None),
        )
        return

    try:
        ack: CaptureAck
        if intent == "capture_voice":
            ack = await client.capture_voice(
                filename=downloaded.filename,
                content=downloaded.content,
                content_type=downloaded.mime_type,
            )
            source_label = "voice"
        else:
            ack = await client.capture_file(
                filename=downloaded.filename,
                content=downloaded.content,
                content_type=downloaded.mime_type,
            )
            source_label = "file"
    except CaptureAPIError as exc:
        log_event(
            "capture_failed",
            level=logging.ERROR,
            intent=intent,
            submitter_hash=submitter_hash,
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
        intent=intent,
        queue_item_id=ack.id,
        submitter_hash=submitter_hash,
    )
    await message.reply_text(
        acknowledgement(ack.id, source_label),
        reply_to_message_id=getattr(message, "message_id", None),
    )
