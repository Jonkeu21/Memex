import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from worker.handlers import file as file_handler
from worker.handlers.exceptions import PermanentHandlerError


def test_binary_image_archived_to_attachments(tmp_vault, tmp_path):
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"\xff\xd8\xff\xe0")
    text, meta, att = file_handler.extract(
        json.dumps({"original_filename": "photo.jpg", "stored_path": str(f),
                    "mime_type": "image/jpeg", "size_bytes": 4}),
        vault_dir=tmp_vault,
        captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
    )
    assert "Binary attachment" in text
    assert att == "_attachments/2026/05/photo.jpg"
    assert (tmp_vault / att).exists()
    assert meta["attachment_only"] is True


def test_binary_collision_renamed(tmp_vault, tmp_path):
    target_dir = tmp_vault / "_attachments" / "2026" / "05"
    target_dir.mkdir(parents=True)
    (target_dir / "photo.jpg").write_bytes(b"old")
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"new")
    _, _, att = file_handler.extract(
        json.dumps({"original_filename": "photo.jpg", "stored_path": str(f), "mime_type": "image/jpeg"}),
        vault_dir=tmp_vault,
        captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
    )
    assert att.endswith("photo-2.jpg")


def test_pdf_extracted_via_pypdf(tmp_vault, tmp_path, monkeypatch):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-fake")

    class FakePage:
        def extract_text(self): return "page text"

    class FakeReader:
        def __init__(self, p): pass
        @property
        def pages(self): return [FakePage(), FakePage()]

    import pypdf  # noqa: F401
    monkeypatch.setattr("pypdf.PdfReader", FakeReader)
    text, _, att = file_handler.extract(
        json.dumps({"stored_path": str(f), "mime_type": "application/pdf",
                    "original_filename": "doc.pdf"}),
        vault_dir=tmp_vault,
        captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
    )
    assert "page text" in text
    assert att is None


def test_pdf_open_failure_permanent(tmp_vault, tmp_path, monkeypatch):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"x")
    def boom(path):
        raise RuntimeError("bad pdf")
    monkeypatch.setattr("pypdf.PdfReader", boom)
    with pytest.raises(PermanentHandlerError):
        file_handler.extract(
            json.dumps({"stored_path": str(f), "mime_type": "application/pdf"}),
            vault_dir=tmp_vault,
            captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        )


def test_pdf_no_text_permanent(tmp_vault, tmp_path, monkeypatch):
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"x")
    class FakePage:
        def extract_text(self): return ""
    class FakeReader:
        def __init__(self, p): pass
        @property
        def pages(self): return [FakePage()]
    monkeypatch.setattr("pypdf.PdfReader", FakeReader)
    with pytest.raises(PermanentHandlerError):
        file_handler.extract(
            json.dumps({"stored_path": str(f), "mime_type": "application/pdf"}),
            vault_dir=tmp_vault,
            captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        )
