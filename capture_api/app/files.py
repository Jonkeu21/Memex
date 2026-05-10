"""File-persistence helpers for /captures/file and /captures/voice.

Atomicity contract: the bytes are streamed to a *temp* file under the inbox,
the queue row is inserted referencing the **eventual** path, then on success
the temp file is ``os.rename``-d into place. If the DB insert fails, the
temp file is removed and no row exists. If the rename fails, the row is
deleted to keep the queue and disk in sync.
"""
from __future__ import annotations

import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO


_BAD_CHARS_RE = re.compile(r"[\x00-\x1f/\\]")
_MAX_NAME_LEN = 200


def sanitise_filename(name: str | None) -> str:
    """Strip path separators, control chars, and dangerous prefixes.

    Rejects ``..``-bearing names. Returns ``"upload.bin"`` for empty input.
    """
    if not name:
        return "upload.bin"
    if "\x00" in name:
        raise ValueError("null byte in filename")
    if ".." in name.replace("\\", "/").split("/"):
        raise ValueError("invalid filename: contains '..'")
    base = os.path.basename(name.replace("\\", "/"))
    if base in ("", ".", ".."):
        raise ValueError("invalid filename")
    cleaned = _BAD_CHARS_RE.sub("_", base).lstrip(".")
    if not cleaned:
        cleaned = "upload.bin"
    if len(cleaned) > _MAX_NAME_LEN:
        stem, _, ext = cleaned.rpartition(".")
        if stem and len(ext) <= 12:
            keep = _MAX_NAME_LEN - len(ext) - 1
            cleaned = f"{stem[:keep]}.{ext}"
        else:
            cleaned = cleaned[:_MAX_NAME_LEN]
    return cleaned


@dataclass(frozen=True)
class StoredUpload:
    final_path: Path
    temp_path: Path
    original_filename: str
    size_bytes: int
    mime_type: str

    def commit(self) -> None:
        self.final_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(self.temp_path, self.final_path)

    def discard(self) -> None:
        for p in (self.temp_path, self.final_path):
            try:
                p.unlink()
            except FileNotFoundError:
                pass


class UploadTooLargeError(Exception):
    pass


def _build_path(inbox_dir: Path, original_filename: str) -> Path:
    now = datetime.now(timezone.utc)
    sub = inbox_dir / f"{now:%Y}" / f"{now:%m}" / f"{now:%d}"
    return sub / f"{uuid.uuid4()}__{original_filename}"


def stream_to_temp(
    src: BinaryIO,
    inbox_dir: Path,
    original_filename: str | None,
    mime_type: str | None,
    max_bytes: int,
    chunk_size: int = 1024 * 1024,
) -> StoredUpload:
    """Stream ``src`` into a temp file under ``inbox_dir``; enforce ``max_bytes``.

    Caller commits the file after a successful DB insert via
    :py:meth:`StoredUpload.commit`, or discards it on error via
    :py:meth:`StoredUpload.discard`.
    """
    safe_name = sanitise_filename(original_filename)
    final_path = _build_path(inbox_dir, safe_name)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = final_path.with_name(final_path.name + ".part")

    written = 0
    try:
        with open(temp_path, "wb") as dst:
            while True:
                chunk = src.read(chunk_size)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    dst.close()
                    try:
                        temp_path.unlink()
                    except FileNotFoundError:
                        pass
                    raise UploadTooLargeError(
                        f"upload exceeded {max_bytes} bytes"
                    )
                dst.write(chunk)
    except Exception:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise

    return StoredUpload(
        final_path=final_path,
        temp_path=temp_path,
        original_filename=safe_name,
        size_bytes=written,
        mime_type=mime_type or "application/octet-stream",
    )


def cleanup_empty_dirs(root: Path, leaf: Path) -> None:
    """Best-effort: remove now-empty date subdirectories under ``root``."""
    try:
        leaf.parent.relative_to(root)
    except ValueError:
        return
    p = leaf.parent
    while p != root and p.exists():
        try:
            p.rmdir()
        except OSError:
            return
        p = p.parent


# Re-exported for tests.
shutil = shutil  # noqa: PLW0127
