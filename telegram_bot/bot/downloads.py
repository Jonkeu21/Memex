"""Telegram file download helpers.

Wraps python-telegram-bot's ``Bot.get_file`` + ``File.download_to_memory`` so
we never persist Telegram payloads to disk; the bytes go straight into the
multipart upload to the capture API. Size is enforced by the bot before the
download is attempted (Telegram returns ``file_size`` on the attachment) and
again after, in case Telegram lies.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any


class DownloadError(RuntimeError):
    """Raised when a Telegram download fails or exceeds the size limit."""


@dataclass
class Downloaded:
    content: bytes
    filename: str
    mime_type: str


async def download_telegram_file(
    *,
    bot: Any,
    file_id: str,
    filename: str,
    mime_type: str,
    max_bytes: int,
    declared_size: int | None = None,
) -> Downloaded:
    """Download a Telegram attachment into memory.

    Args:
        bot: a python-telegram-bot ``Bot`` instance (or compatible double).
        file_id: Telegram file_id from the attachment.
        filename: filename to advertise to the capture API.
        mime_type: MIME type to advertise to the capture API.
        max_bytes: hard size cap; raises ``DownloadError`` if exceeded.
        declared_size: optional ``file_size`` from Telegram for fast-fail.
    """
    if declared_size is not None and declared_size > max_bytes:
        raise DownloadError(
            f"file too large: {declared_size} bytes > {max_bytes} bytes"
        )
    try:
        tg_file = await bot.get_file(file_id)
        buf = BytesIO()
        await tg_file.download_to_memory(out=buf)
    except Exception as exc:  # noqa: BLE001 — Telegram raises a wide variety
        raise DownloadError(f"telegram download failed: {exc}") from exc
    data = buf.getvalue()
    if len(data) > max_bytes:
        raise DownloadError(f"file too large after download: {len(data)} bytes > {max_bytes}")
    return Downloaded(content=data, filename=filename, mime_type=mime_type)
