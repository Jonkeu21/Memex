"""Intent detection per CLAUDE.md "Telegram bot contract".

Six rules, evaluated in order, first match wins:

1. Message has a document, audio, voice, video, or photo attachment → capture.
2. Text matches the bare-URL regex (single URL, optional surrounding whitespace) → capture-url.
3. Text contains any URL alongside other text → capture-url with the URL extracted and the rest stored as user_note.
4. Text ends with ``?`` (after stripping trailing whitespace) → retrieval.
5. Text starts with one of the question words (case-insensitive, word-boundary) → retrieval.
6. Otherwise → capture as text.

Commands (text starting with ``/``) are routed by python-telegram-bot's
CommandHandler before this module is consulted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Intent(str, Enum):
    CAPTURE_ATTACHMENT = "capture_attachment"
    CAPTURE_URL = "capture_url"
    RETRIEVAL = "retrieval"
    CAPTURE_TEXT = "capture_text"


@dataclass(frozen=True)
class Decision:
    intent: Intent
    # For CAPTURE_URL: the URL to forward.
    url: str | None = None
    # For CAPTURE_URL rule 3: free-text remnant after URL is removed.
    user_note: str | None = None
    # For all text-bearing intents: the raw text the user sent.
    text: str | None = None


# A single bare URL (rule 2). Anchors on whole string, optional surrounding whitespace.
_BARE_URL_RE = re.compile(r"^\s*(https?://\S+)\s*$", re.IGNORECASE)
# Any URL embedded in text (rule 3).
_ANY_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
# Question-word prefix (rule 5). Case-insensitive, word-boundary.
_QUESTION_WORDS = ("who", "what", "when", "where", "why", "how", "which", "find", "show", "recall", "remind")
_QUESTION_PREFIX_RE = re.compile(
    r"^\s*(?:" + "|".join(_QUESTION_WORDS) + r")\b",
    re.IGNORECASE,
)


def has_attachment(message: Any) -> bool:
    """Return True if the message carries an attachment per CLAUDE.md rule 1.

    The contract names: document, audio, voice, video, photo. python-telegram-bot
    exposes each as an attribute on the Message object; missing/empty means
    no attachment of that kind.
    """
    if message is None:
        return False
    for attr in ("document", "audio", "voice", "video"):
        if getattr(message, attr, None):
            return True
    photo = getattr(message, "photo", None)
    if photo:
        return True
    return False


def classify_text(text: str) -> Decision:
    """Classify a text-only message body.

    Pure function; no Telegram types in the signature so it is trivial to test.
    """
    if text is None:
        return Decision(Intent.CAPTURE_TEXT, text="")

    # Rule 2: bare URL.
    bare = _BARE_URL_RE.match(text)
    if bare:
        return Decision(Intent.CAPTURE_URL, url=bare.group(1), text=text)

    # Rule 3: URL alongside other text.
    embedded = _ANY_URL_RE.search(text)
    if embedded:
        url = embedded.group(0)
        remnant = (text[: embedded.start()] + text[embedded.end() :]).strip()
        return Decision(
            Intent.CAPTURE_URL,
            url=url,
            user_note=remnant or None,
            text=text,
        )

    stripped = text.rstrip()
    # Rule 4: ends with '?'.
    if stripped.endswith("?"):
        return Decision(Intent.RETRIEVAL, text=text)

    # Rule 5: question-word prefix.
    if _QUESTION_PREFIX_RE.match(text):
        return Decision(Intent.RETRIEVAL, text=text)

    # Rule 6: default.
    return Decision(Intent.CAPTURE_TEXT, text=text)


def classify(message: Any) -> Decision:
    """Classify a Telegram message object end-to-end.

    Rule 1 is checked first. If no attachment, defers to ``classify_text``
    on ``message.text``.
    """
    if has_attachment(message):
        return Decision(Intent.CAPTURE_ATTACHMENT)
    text = getattr(message, "text", None) or ""
    return classify_text(text)
