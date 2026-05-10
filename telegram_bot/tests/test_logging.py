"""Logger formatting, redaction, secret-leakage avoidance."""
from __future__ import annotations

import json
import logging

from bot.logging import JsonFormatter, configure, hash_chat_id, log_event, redact


def _last_json_line(captured: str) -> dict:
    lines = [ln for ln in captured.strip().splitlines() if ln.startswith("{")]
    assert lines, f"no JSON log lines in capture: {captured!r}"
    return json.loads(lines[-1])


def test_redact_masks_secret_keys():
    out = redact({"authorization": "Bearer abc", "password": "x", "ok": 1})
    assert out["authorization"] == "***"
    assert out["password"] == "***"
    assert out["ok"] == 1


def test_redact_replaces_body_with_size():
    out = redact({"text": "hello"})
    assert "text" not in out
    assert out["text_size_bytes"] == 5


def test_redact_recurses_into_lists_and_dicts():
    out = redact({"items": [{"token": "x"}, {"text": "ab"}]})
    assert out["items"][0]["token"] == "***"
    assert out["items"][1]["text_size_bytes"] == 2


def test_hash_chat_id_stable_and_short():
    h1 = hash_chat_id(4242)
    h2 = hash_chat_id("4242")
    assert h1 == h2
    assert len(h1) == 12


def test_log_event_payload_shape(capsys):
    configure("DEBUG")
    log_event("test_event", queue_item_id=42, foo="bar")
    payload = _last_json_line(capsys.readouterr().out)
    assert payload["service"] == "telegram_bot"
    assert payload["event"] == "test_event"
    assert payload["level"] == "info"
    assert payload["queue_item_id"] == 42
    assert payload["foo"] == "bar"
    assert "ts" in payload


def test_log_event_redacts_token_in_extras(capsys):
    configure("DEBUG")
    log_event("call_made", api_token="secret-xyz", duration_ms=10)
    raw = capsys.readouterr().out
    payload = _last_json_line(raw)
    assert payload["api_token"] == "***"
    assert "secret-xyz" not in raw


def test_log_event_warn_level_renders_correctly(capsys):
    configure("DEBUG")
    log_event("uh_oh", level=logging.WARNING, why="test")
    payload = _last_json_line(capsys.readouterr().out)
    assert payload["level"] == "warn"


def test_formatter_includes_traceback_on_exception():
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        exc_info = sys.exc_info()
        record = logging.LogRecord(
            "telegram_bot", logging.ERROR, __file__, 0, "broken", None, exc_info
        )
        record.event = "broken"
        rendered = formatter.format(record)
        payload = json.loads(rendered)
        assert payload["error"]["type"] == "ValueError"
        assert payload["error"]["message"] == "boom"
        assert "traceback" in payload
