import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from worker.handlers import file as file_handler
from worker.handlers.exceptions import PermanentHandlerError


def test_text_file_extension(tmp_vault, tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("Plain text body.", encoding="utf-8")
    text, meta, att = file_handler.extract(
        json.dumps({"original_filename": "note.txt", "stored_path": str(f),
                    "mime_type": None, "size_bytes": 17}),
        vault_dir=tmp_vault,
        captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
    )
    assert text == "Plain text body."
    assert att is None
    assert meta["original_filename"] == "note.txt"


def test_text_file_via_mime(tmp_vault, tmp_path):
    f = tmp_path / "note"
    f.write_text("Hi.", encoding="utf-8")
    text, meta, att = file_handler.extract(
        json.dumps({"original_filename": "note", "stored_path": str(f),
                    "mime_type": "text/plain", "size_bytes": 3}),
        vault_dir=tmp_vault,
        captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
    )
    assert text == "Hi."
    assert att is None


def test_markdown_file(tmp_vault, tmp_path):
    f = tmp_path / "note.md"
    f.write_text("# H\nbody", encoding="utf-8")
    text, _, att = file_handler.extract(
        json.dumps({"stored_path": str(f), "mime_type": None}),
        vault_dir=tmp_vault,
        captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
    )
    assert text.startswith("# H")
    assert att is None


def test_empty_text_file_permanent(tmp_vault, tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("", encoding="utf-8")
    with pytest.raises(PermanentHandlerError):
        file_handler.extract(
            json.dumps({"stored_path": str(f), "mime_type": "text/plain"}),
            vault_dir=tmp_vault,
            captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        )


def test_missing_file_permanent(tmp_vault, tmp_path):
    with pytest.raises(PermanentHandlerError):
        file_handler.extract(
            json.dumps({"stored_path": str(tmp_path / "missing.txt"), "mime_type": "text/plain"}),
            vault_dir=tmp_vault,
            captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        )


def test_missing_stored_path_field_permanent(tmp_vault):
    with pytest.raises(PermanentHandlerError):
        file_handler.extract(
            json.dumps({}),
            vault_dir=tmp_vault,
            captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        )


def test_text_file_invalid_utf8_falls_back(tmp_vault, tmp_path):
    f = tmp_path / "bad.txt"
    f.write_bytes(b"good \xff\xfe end")
    text, _, _ = file_handler.extract(
        json.dumps({"stored_path": str(f), "mime_type": "text/plain"}),
        vault_dir=tmp_vault,
        captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
    )
    assert "good" in text
    assert "end" in text
