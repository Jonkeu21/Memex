from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import pytest

from app.files import (
    StoredUpload,
    UploadTooLargeError,
    sanitise_filename,
    stream_to_temp,
)
from app.logging import JsonFormatter, configure, hash_chat_id, redact


def test_sanitise_filename_basics() -> None:
    assert sanitise_filename("scan.pdf") == "scan.pdf"
    assert sanitise_filename(None) == "upload.bin"
    assert sanitise_filename("") == "upload.bin"


def test_sanitise_strips_dirs() -> None:
    assert "/" not in sanitise_filename("a/b/c.pdf")


def test_sanitise_rejects_traversal() -> None:
    with pytest.raises(ValueError):
        sanitise_filename("..")
    with pytest.raises(ValueError):
        sanitise_filename("foo/../bar")


def test_sanitise_rejects_null_byte() -> None:
    with pytest.raises(ValueError):
        sanitise_filename("a\x00b.pdf")


def test_sanitise_long_name() -> None:
    name = "a" * 300 + ".pdf"
    out = sanitise_filename(name)
    assert len(out) <= 200
    assert out.endswith(".pdf")


def test_sanitise_long_name_no_short_ext() -> None:
    name = "x" * 300
    out = sanitise_filename(name)
    assert len(out) == 200


def test_sanitise_strips_leading_dot() -> None:
    assert sanitise_filename(".hidden") == "hidden"


def test_stream_to_temp_writes_and_commits(tmp_path: Path) -> None:
    src = io.BytesIO(b"data" * 100)
    stored: StoredUpload = stream_to_temp(
        src,
        inbox_dir=tmp_path,
        original_filename="x.bin",
        mime_type="application/octet-stream",
        max_bytes=1024,
    )
    assert stored.size_bytes == 400
    assert stored.temp_path.exists()
    assert not stored.final_path.exists()
    stored.commit()
    assert stored.final_path.exists()
    assert not stored.temp_path.exists()


def test_stream_to_temp_too_large(tmp_path: Path) -> None:
    src = io.BytesIO(b"x" * 1024)
    with pytest.raises(UploadTooLargeError):
        stream_to_temp(
            src,
            inbox_dir=tmp_path,
            original_filename="x.bin",
            mime_type=None,
            max_bytes=10,
        )
    leftover = list(tmp_path.rglob("*"))
    assert [p for p in leftover if p.is_file()] == []


def test_stored_discard_removes_files(tmp_path: Path) -> None:
    src = io.BytesIO(b"abc")
    stored = stream_to_temp(
        src, inbox_dir=tmp_path, original_filename="x.bin", mime_type=None, max_bytes=1024
    )
    stored.discard()
    assert not stored.temp_path.exists()
    assert not stored.final_path.exists()


def test_redact_hides_secrets() -> None:
    out = redact({"token": "abc", "Authorization": "Bearer x", "ok": 1})
    assert out["token"] == "***"
    assert out["Authorization"] == "***"
    assert out["ok"] == 1


def test_redact_replaces_text_body() -> None:
    out = redact({"text": "hello world"})
    assert "text" not in out
    assert out["text_size_bytes"] == len("hello world")


def test_redact_recurses_into_lists() -> None:
    out = redact({"items": [{"password": "x"}]})
    assert out["items"][0]["password"] == "***"


def test_hash_chat_id_stable() -> None:
    a = hash_chat_id(123)
    b = hash_chat_id("123")
    assert a == b and len(a) == 12


def test_json_formatter_emits_required_fields(caplog: pytest.LogCaptureFixture) -> None:
    configure("DEBUG")
    fmt = JsonFormatter()
    rec = logging.LogRecord(
        name="capture_api", level=logging.INFO, pathname="x.py", lineno=1,
        msg="hello", args=(), exc_info=None
    )
    rec.event = "demo"  # type: ignore[attr-defined]
    rec.extras = {"queue_item_id": 42}  # type: ignore[attr-defined]
    out = json.loads(fmt.format(rec))
    assert out["service"] == "capture_api"
    assert out["event"] == "demo"
    assert out["level"] == "info"
    assert out["queue_item_id"] == 42
    assert out["ts"].endswith("Z")


def test_json_formatter_includes_error_on_exc(caplog: pytest.LogCaptureFixture) -> None:
    fmt = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        rec = logging.LogRecord(
            name="capture_api", level=logging.ERROR, pathname="x.py", lineno=1,
            msg="oops", args=(), exc_info=sys.exc_info()
        )
        out = json.loads(fmt.format(rec))
    assert out["error"]["type"] == "ValueError"
    assert "traceback" in out
