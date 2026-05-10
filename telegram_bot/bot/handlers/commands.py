"""Command handlers per CLAUDE.md.

The contract registers exactly six commands: ``/start``, ``/help``, ``/queue``,
``/last``, ``/find <query>``, ``/capture <text>``. No others are bound.
"""
from __future__ import annotations

import logging
from typing import Any

from ..capture_client import CaptureClient
from ..config import Settings
from ..logging import hash_chat_id, log_event
from ..queue_reader import (
    QueueUnavailable,
    recent_items,
    status_counts_24h,
)
from .capture_text import handle_capture_text
from .retrieval import handle_retrieval

GREETING = (
    "Hi — I'm Memex. Send me a URL, a file, a voice note, or some text and "
    "I'll queue it. Ask me a question (or use /find) to search the vault.\n\n"
    "Commands: /start /help /queue /last /find <query> /capture <text>"
)


def _command_args(message: Any) -> str:
    """Return the message text after the command word."""
    text = (getattr(message, "text", None) or "").strip()
    if not text:
        return ""
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else ""


async def cmd_start(message: Any) -> None:
    log_event(
        "command_received",
        intent="cmd_start",
        submitter_hash=hash_chat_id(getattr(message.chat, "id", "unknown")),
    )
    await message.reply_text(GREETING)


async def cmd_help(message: Any) -> None:
    log_event(
        "command_received",
        intent="cmd_help",
        submitter_hash=hash_chat_id(getattr(message.chat, "id", "unknown")),
    )
    await message.reply_text(GREETING)


async def cmd_queue(message: Any, *, settings: Settings) -> None:
    chat_id = getattr(message.chat, "id", "unknown")
    log_event(
        "command_received",
        intent="cmd_queue",
        submitter_hash=hash_chat_id(chat_id),
    )
    try:
        counts = status_counts_24h(settings.db_path)
    except QueueUnavailable as exc:
        log_event(
            "queue_read_failed",
            level=logging.WARNING,
            intent="cmd_queue",
            error_message=str(exc),
        )
        await message.reply_text("Queue is unavailable right now.")
        return
    body = (
        "*Last 24h*\n"
        f"queued: {counts.queued}\n"
        f"processing: {counts.processing}\n"
        f"filed: {counts.filed}\n"
        f"needs_review: {counts.needs_review}\n"
        f"failed: {counts.failed}"
    )
    await message.reply_text(body, parse_mode="Markdown")


async def cmd_last(message: Any, *, settings: Settings) -> None:
    chat_id = getattr(message.chat, "id", "unknown")
    log_event(
        "command_received",
        intent="cmd_last",
        submitter_hash=hash_chat_id(chat_id),
    )
    try:
        items = recent_items(settings.db_path, limit=5)
    except QueueUnavailable as exc:
        log_event(
            "queue_read_failed",
            level=logging.WARNING,
            intent="cmd_last",
            error_message=str(exc),
        )
        await message.reply_text("Queue is unavailable right now.")
        return
    if not items:
        await message.reply_text("No captures yet.")
        return
    lines = ["*Most recent captures*"]
    for it in items:
        path = it.vault_path or "(pending)"
        lines.append(f"#{it.id} [{it.status}] {it.source_type} → {path}")
    await message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_find(
    message: Any,
    *,
    settings: Settings,
    prompt_template: str,
    record_call: Any = None,
    runner: Any = None,
) -> None:
    """Force retrieval intent regardless of message shape."""
    chat_id = getattr(message.chat, "id", "unknown")
    log_event(
        "command_received",
        intent="cmd_find",
        submitter_hash=hash_chat_id(chat_id),
    )
    query = _command_args(message)
    if not query:
        await message.reply_text("Usage: /find <your question>")
        return
    await handle_retrieval(
        message=message,
        question=query,
        settings=settings,
        prompt_template=prompt_template,
        record_call=record_call,
        runner=runner,
    )


async def cmd_capture(
    message: Any,
    *,
    client: CaptureClient,
) -> None:
    """Force text-capture intent regardless of message shape."""
    chat_id = getattr(message.chat, "id", "unknown")
    log_event(
        "command_received",
        intent="cmd_capture",
        submitter_hash=hash_chat_id(chat_id),
    )
    body = _command_args(message)
    if not body:
        await message.reply_text("Usage: /capture <text to save>")
        return
    await handle_capture_text(message=message, text=body, client=client)
