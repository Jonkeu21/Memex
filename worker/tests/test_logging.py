import json
import logging

from worker.logging import (
    JsonFormatter,
    configure,
    hash_chat_id,
    log_event,
    redact,
)


def test_redact_secret_keys():
    payload = {"api_key": "abc", "Authorization": "Bearer x", "ok": 1}
    out = redact(payload)
    assert out["api_key"] == "***"
    assert out["Authorization"] == "***"
    assert out["ok"] == 1


def test_redact_replaces_text_body_with_size():
    payload = {"text": "hello"}
    out = redact(payload)
    assert "text" not in out
    assert out["text_size_bytes"] == 5


def test_redact_recurses_into_lists():
    payload = [{"token": "secret"}, {"ok": 1}]
    out = redact(payload)
    assert out[0]["token"] == "***"


def test_hash_chat_id_deterministic():
    h1 = hash_chat_id(123)
    h2 = hash_chat_id("123")
    assert h1 == h2
    assert len(h1) == 12


def test_log_event_emits_json(capsys):
    configure("INFO")
    log_event("item_processed", queue_item_id=42, status="filed", confidence=0.9)
    captured = capsys.readouterr().out.strip().splitlines()
    assert captured, "no log line emitted"
    last = json.loads(captured[-1])
    assert last["event"] == "item_processed"
    assert last["service"] == "worker"
    assert last["level"] == "info"
    assert last["queue_item_id"] == 42


def test_json_formatter_carries_exception_info():
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = logging.LogRecord(
            "worker", logging.ERROR, __file__, 1, "evt", (), sys.exc_info(),
        )
    record.event = "evt"
    out = json.loads(formatter.format(record))
    assert out["error"]["type"] == "ValueError"
    assert "boom" in out["error"]["message"]
    assert "traceback" in out
