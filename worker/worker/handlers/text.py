"""Plain-text source handler — pass-through."""
from __future__ import annotations

import json
from typing import Any


def extract(source_payload: str) -> tuple[str, dict[str, Any], str | None]:
    payload = json.loads(source_payload)
    text = payload.get("text", "")
    if not isinstance(text, str):
        text = str(text)
    return text, {"length": len(text)}, None
