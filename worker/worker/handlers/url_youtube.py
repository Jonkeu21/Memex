"""YouTube transcript extractor via yt-dlp.

Tries to download auto-generated English subtitles. If none are produced,
raises :class:`PermanentHandlerError` and the worker writes an inbox stub
note with ``extraction_failed: true`` in the front-matter.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from worker.handlers.exceptions import PermanentHandlerError, TransientHandlerError

YT_DLP_BIN = "yt-dlp"


def _run_ytdlp(url: str, out_dir: Path, runner: Any) -> None:
    args = [
        YT_DLP_BIN,
        "--write-auto-sub",
        "--skip-download",
        "--sub-lang", "en",
        "--convert-subs", "srt",
        "-o", str(out_dir / "%(id)s.%(ext)s"),
        url,
    ]
    try:
        result = runner(args, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise TransientHandlerError(f"yt-dlp timed out: {exc}") from exc
    except FileNotFoundError as exc:
        raise TransientHandlerError(f"yt-dlp not found: {exc}") from exc
    if result.returncode != 0:
        raise TransientHandlerError(
            f"yt-dlp exited {result.returncode}: {(result.stderr or '')[:500]}"
        )


def _parse_srt(srt_text: str) -> str:
    lines: list[str] = []
    for raw in srt_text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.isdigit():
            continue
        if "-->" in s:
            continue
        lines.append(s)
    return "\n".join(lines)


def extract(
    source_payload: str,
    *,
    runner: Any | None = None,
) -> tuple[str, dict[str, Any], str | None]:
    payload = json.loads(source_payload)
    url = payload.get("url")
    if not isinstance(url, str) or not url:
        raise PermanentHandlerError("source_payload.url missing")
    runner = runner or subprocess.run

    with tempfile.TemporaryDirectory(prefix="memex-yt-") as tmp:
        tmp_dir = Path(tmp)
        _run_ytdlp(url, tmp_dir, runner)
        srt_files = list(tmp_dir.glob("*.en.srt"))
        if not srt_files:
            raise PermanentHandlerError(f"no transcript produced for {url}")
        srt_text = srt_files[0].read_text(encoding="utf-8", errors="replace")
        text = _parse_srt(srt_text)
        if not text:
            raise PermanentHandlerError(f"empty transcript for {url}")

    metadata: dict[str, Any] = {
        "url": url,
        "host": urlparse(url).hostname or "",
        "youtube": True,
    }
    return text, metadata, None
