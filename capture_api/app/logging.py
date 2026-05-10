"""Structured JSON logger emitting one object per line to stdout.

Format and redaction rules follow CLAUDE.md "Error handling & logging".
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

SERVICE_NAME = "capture_api"

_SECRET_KEY_RE = re.compile(r"(?i)token|secret|api[_-]?key|password|authorization")
_BODY_KEYS = {"text", "body", "content", "raw"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def redact(value: Any) -> Any:
    """Recursively redact secret-shaped fields and large bodies in a payload."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and _SECRET_KEY_RE.search(k):
                out[k] = "***"
            elif isinstance(k, str) and k in _BODY_KEYS and isinstance(v, str):
                out[f"{k}_size_bytes"] = len(v.encode("utf-8"))
            else:
                out[k] = redact(v)
        return out
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def hash_chat_id(chat_id: str | int) -> str:
    return hashlib.sha256(str(chat_id).encode("utf-8")).hexdigest()[:12]


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: dict[str, Any] = {
            "ts": _utc_now_iso(),
            "service": SERVICE_NAME,
            "level": record.levelname.lower().replace("warning", "warn"),
            "event": getattr(record, "event", record.getMessage()),
        }
        extras = getattr(record, "extras", None)
        if isinstance(extras, dict):
            payload.update(redact(extras))
        if record.exc_info:
            etype, evalue, _ = record.exc_info
            payload["error"] = {
                "type": etype.__name__ if etype else "Exception",
                "message": str(evalue) if evalue else "",
            }
            payload["traceback"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), default=str)


_configured = False


def configure(level: str = "INFO") -> logging.Logger:
    global _configured
    root = logging.getLogger()
    if not _configured:
        for h in list(root.handlers):
            root.removeHandler(h)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
        _configured = True
    root.setLevel(level.replace("WARN", "WARNING"))
    logging.getLogger("uvicorn.access").propagate = False
    return get_logger()


def get_logger() -> logging.Logger:
    return logging.getLogger("capture_api")


def log_event(event: str, level: int = logging.INFO, **fields: Any) -> None:
    logger = get_logger()
    logger.log(level, event, extra={"event": event, "extras": fields})
