import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from worker.handlers import voice
from worker.handlers.exceptions import PermanentHandlerError, TransientHandlerError


class _FakeProc:
    def __init__(self, returncode=0, stderr=""):
        self.stdout = ""
        self.stderr = stderr
        self.returncode = returncode


def _runner_writes_txt(transcript: str, returncode: int = 0):
    def runner(args, **kw):
        # whisper-cpp writes <audio>.txt by default
        f_idx = args.index("-f") + 1
        audio = Path(args[f_idx])
        audio.with_suffix(audio.suffix + ".txt").write_text(transcript, encoding="utf-8")
        return _FakeProc(returncode=returncode)
    return runner


def test_voice_happy(tmp_vault, tmp_path):
    audio = tmp_path / "voice.ogg"
    audio.write_bytes(b"\x00\x01")
    captured_at = datetime(2026, 5, 10, tzinfo=timezone.utc)
    text, meta, att = voice.extract(
        json.dumps({"original_filename": "voice.ogg", "stored_path": str(audio),
                    "mime_type": "audio/ogg", "duration_seconds": 5.0}),
        vault_dir=tmp_vault,
        captured_at=captured_at,
        whisper_bin="whisper-cpp",
        whisper_model=tmp_path / "model.bin",
        runner=_runner_writes_txt("Hello there.\n"),
    )
    assert text == "Hello there."
    assert att == "_attachments/2026/05/voice.ogg"
    assert (tmp_vault / att).exists()
    assert not audio.exists()  # moved


def test_voice_collision_renames(tmp_vault, tmp_path):
    target_dir = tmp_vault / "_attachments" / "2026" / "05"
    target_dir.mkdir(parents=True)
    (target_dir / "voice.ogg").write_bytes(b"old")
    audio = tmp_path / "voice.ogg"
    audio.write_bytes(b"new")
    text, _, att = voice.extract(
        json.dumps({"stored_path": str(audio), "original_filename": "voice.ogg"}),
        vault_dir=tmp_vault,
        captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        whisper_bin="w", whisper_model=tmp_path / "m.bin",
        runner=_runner_writes_txt("hi"),
    )
    assert att.endswith("voice-2.ogg")


def test_voice_missing_audio_permanent(tmp_vault, tmp_path):
    with pytest.raises(PermanentHandlerError):
        voice.extract(
            json.dumps({"stored_path": str(tmp_path / "missing.ogg")}),
            vault_dir=tmp_vault,
            captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
            whisper_bin="w", whisper_model=tmp_path / "m.bin",
        )


def test_voice_missing_field_permanent(tmp_vault, tmp_path):
    with pytest.raises(PermanentHandlerError):
        voice.extract(
            json.dumps({}),
            vault_dir=tmp_vault,
            captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
            whisper_bin="w", whisper_model=tmp_path / "m.bin",
        )


def test_voice_whisper_nonzero_transient(tmp_vault, tmp_path):
    audio = tmp_path / "voice.ogg"
    audio.write_bytes(b"x")
    def runner(args, **kw):
        return _FakeProc(returncode=1, stderr="bad")
    with pytest.raises(TransientHandlerError):
        voice.extract(
            json.dumps({"stored_path": str(audio)}),
            vault_dir=tmp_vault,
            captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
            whisper_bin="w", whisper_model=tmp_path / "m.bin",
            runner=runner,
        )


def test_voice_whisper_timeout_transient(tmp_vault, tmp_path):
    audio = tmp_path / "voice.ogg"
    audio.write_bytes(b"x")
    def runner(args, **kw):
        raise subprocess.TimeoutExpired(cmd="w", timeout=1)
    with pytest.raises(TransientHandlerError):
        voice.extract(
            json.dumps({"stored_path": str(audio)}),
            vault_dir=tmp_vault,
            captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
            whisper_bin="w", whisper_model=tmp_path / "m.bin",
            runner=runner,
        )


def test_voice_whisper_no_txt_transient(tmp_vault, tmp_path):
    audio = tmp_path / "voice.ogg"
    audio.write_bytes(b"x")
    def runner(args, **kw):
        return _FakeProc(returncode=0)
    with pytest.raises(TransientHandlerError):
        voice.extract(
            json.dumps({"stored_path": str(audio)}),
            vault_dir=tmp_vault,
            captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
            whisper_bin="w", whisper_model=tmp_path / "m.bin",
            runner=runner,
        )


def test_voice_empty_transcript_permanent(tmp_vault, tmp_path):
    audio = tmp_path / "voice.ogg"
    audio.write_bytes(b"x")
    with pytest.raises(PermanentHandlerError):
        voice.extract(
            json.dumps({"stored_path": str(audio)}),
            vault_dir=tmp_vault,
            captured_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
            whisper_bin="w", whisper_model=tmp_path / "m.bin",
            runner=_runner_writes_txt(""),
        )
