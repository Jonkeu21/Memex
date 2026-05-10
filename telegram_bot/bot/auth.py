"""Chat-ID whitelist enforcement.

Per CLAUDE.md: messages from non-whitelisted chats are silently dropped with
a debug log. The bot never replies to non-whitelisted chats — not even with
an "unauthorized" message.
"""
from __future__ import annotations

import logging
from typing import Iterable

from .logging import hash_chat_id, log_event


def is_allowed(chat_id: int | None, allowed: Iterable[int]) -> bool:
    if chat_id is None:
        return False
    return chat_id in set(allowed)


def log_rejection(chat_id: int | None) -> None:
    log_event(
        "chat_rejected",
        level=logging.WARNING,
        submitter_hash=hash_chat_id(chat_id if chat_id is not None else "unknown"),
    )
