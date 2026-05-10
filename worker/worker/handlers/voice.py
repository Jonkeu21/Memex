"""Voice handler — whisper.cpp transcription + audio archival."""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from worker.handlers.exceptions import PermanentHandlerError, TransientHandlerError


def _run_whisper(
    *,
    whisper_bin: str,
    model_path: Path,
    audio_path: Path,
    runner: Any,
) -> Path:
    args = [whisper_bin, "-m", str(model_path), "-f", str(audio_path), "-otxt"]
    try:
        result = runner(args, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired as exc:
        raise TransientHandlerError(f"whisper-cpp timed out: {exc}") from exc
    except FileNotFoundError as exc:
        raise TransientHandlerError(f"whisper-cpp not found: {exc}") from exc
    if result.returncode != 0:
        raise TransientHandlerError(
            f"whisper-cpp exited {result.returncode}: {(result.stderr or '')[:500]}"
        )
    txt_path = audio_path.with_suffix(audio_path.suffix + ".txt")
    if not txt_path.exists():
        alt = audio_path.with_suffix(".txt")
        if alt.exists():
            return alt
        raise TransientHandlerError(f"whisper-cpp produced no .txt for {audio_path}")
    return txt_path


def _archive_audio(audio_path: Path, vault_dir: Path, captured_at: datetime) -> str:
    yyyy = f"{captured_at.year:04d}"
    mm = f"{captured_at.month:02d}"
    target_dir = vault_dir / "_attachments" / yyyy / mm
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / audio_path.name
    n = 2
    while target.exists():
        target = target_dir / f"{audio_path.stem}-{n}{audio_path.suffix}"
        n += 1
    shutil.move(str(audio_path), target)
    return f"_attachments/{yyyy}/{mm}/{target.name}"


def extract(
    source_payload: str,
    *,
    vault_dir: Path,
    captured_at: datetime,
    whisper_bin: str,
    whisper_model: Path,
    runner: Any | None = None,
) -> tuple[str, dict[str, Any], str | None]:
    payload = json.loads(source_payload)
    stored = payload.get("stored_path")
    if not isinstance(stored, str) or not stored:
        raise PermanentHandlerError("voice payload missing stored_path")
    audio = Path(stored)
    if not audio.exists():
        raise PermanentHandlerError(f"voice audio missing on disk: {audio}")

    runner = runner or subprocess.run
    txt_path = _run_whisper(
        whisper_bin=whisper_bin,
        model_path=whisper_model,
        audio_path=audio,
        runner=runner,
    )
    text = txt_path.read_text(encoding="utf-8", errors="replace").strip()
    try:
        txt_path.unlink()
    except FileNotFoundError:
        pass
    if not text:
        raise PermanentHandlerError(f"empty transcript for {audio}")

    attachment_rel = _archive_audio(audio, vault_dir, captured_at)
    metadata: dict[str, Any] = {
        "original_filename": payload.get("original_filename"),
        "mime_type": payload.get("mime_type"),
        "duration_seconds": payload.get("duration_seconds"),
    }
    return text, metadata, attachment_rel
