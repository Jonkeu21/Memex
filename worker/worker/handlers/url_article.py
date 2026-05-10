"""URL article extractor.

Dispatches to :mod:`url_youtube` for YouTube hosts, otherwise falls back to
``trafilatura``. Importing trafilatura inside the function lets tests patch it.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from worker.handlers import url_youtube
from worker.handlers.exceptions import PermanentHandlerError, TransientHandlerError

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def is_youtube(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in YOUTUBE_HOSTS


def _fetch_with_trafilatura(url: str) -> str:
    try:
        import trafilatura  # type: ignore
    except ImportError as exc:
        raise TransientHandlerError(f"trafilatura unavailable: {exc}") from exc
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise TransientHandlerError(f"trafilatura.fetch_url returned empty for {url}")
    text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
    if not text:
        raise PermanentHandlerError(f"trafilatura.extract returned empty for {url}")
    return text


def extract(source_payload: str) -> tuple[str, dict[str, Any], str | None]:
    payload = json.loads(source_payload)
    url = payload.get("url")
    if not isinstance(url, str) or not url:
        raise PermanentHandlerError("source_payload.url missing")
    user_note = payload.get("user_note") or ""

    if is_youtube(url):
        text, meta, attachment = url_youtube.extract(source_payload)
        meta = {**meta, "user_note": user_note} if user_note else meta
        return text, meta, attachment

    text = _fetch_with_trafilatura(url)
    metadata: dict[str, Any] = {"url": url, "host": urlparse(url).hostname or ""}
    if user_note:
        metadata["user_note"] = user_note
    return text, metadata, None
