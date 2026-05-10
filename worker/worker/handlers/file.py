"""File handler — dispatches by MIME / extension."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from worker.handlers.exceptions import PermanentHandlerError, TransientHandlerError

TEXT_EXTS = {".txt", ".md", ".markdown", ".rst", ".log"}
PDF_EXTS = {".pdf"}


def _is_text_mime(mime: str | None) -> bool:
    if not mime:
        return False
    return mime.startswith("text/") or mime in {"application/json", "application/xml"}


def _archive_binary(file_path: Path, vault_dir: Path, captured_at: datetime) -> str:
    yyyy = f"{captured_at.year:04d}"
    mm = f"{captured_at.month:02d}"
    target_dir = vault_dir / "_attachments" / yyyy / mm
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / file_path.name
    n = 2
    while target.exists():
        target = target_dir / f"{file_path.stem}-{n}{file_path.suffix}"
        n += 1
    shutil.copy2(file_path, target)
    return f"_attachments/{yyyy}/{mm}/{target.name}"


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:
        raise TransientHandlerError(f"pypdf unavailable: {exc}") from exc
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise PermanentHandlerError(f"pypdf failed to open {path}: {exc}") from exc
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n\n".join(p for p in parts if p)
    if not text.strip():
        raise PermanentHandlerError(f"pdf yielded no extractable text: {path}")
    return text


def extract(
    source_payload: str,
    *,
    vault_dir: Path,
    captured_at: datetime,
) -> tuple[str, dict[str, Any], str | None]:
    payload = json.loads(source_payload)
    stored = payload.get("stored_path")
    if not isinstance(stored, str) or not stored:
        raise PermanentHandlerError("file payload missing stored_path")
    path = Path(stored)
    if not path.exists():
        raise PermanentHandlerError(f"file missing on disk: {path}")

    mime = payload.get("mime_type")
    original_filename = payload.get("original_filename") or path.name
    ext = path.suffix.lower()

    metadata: dict[str, Any] = {
        "original_filename": original_filename,
        "mime_type": mime,
        "size_bytes": payload.get("size_bytes"),
    }

    if ext in TEXT_EXTS or _is_text_mime(mime):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            raise PermanentHandlerError(f"text file is empty: {path}")
        return text, metadata, None

    if ext in PDF_EXTS or mime == "application/pdf":
        text = _extract_pdf(path)
        return text, metadata, None

    attachment = _archive_binary(path, vault_dir, captured_at)
    stub = (
        f"Binary attachment: {original_filename}\n"
        f"MIME: {mime or 'unknown'}\n"
        f"Stored at vault path: {attachment}\n"
    )
    metadata["attachment_only"] = True
    return stub, metadata, attachment
