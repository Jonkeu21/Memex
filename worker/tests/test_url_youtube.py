import json
import subprocess
from pathlib import Path

import pytest

from worker.handlers import url_youtube
from worker.handlers.exceptions import PermanentHandlerError, TransientHandlerError


class _FakeProc:
    def __init__(self, returncode=0, stderr=""):
        self.stdout = ""
        self.stderr = stderr
        self.returncode = returncode


def _make_runner_writing_srt(srt_text: str, *, returncode: int = 0):
    def runner(args, capture_output=True, text=True, timeout=None):
        out_idx = args.index("-o") + 1
        template = args[out_idx]
        out_dir = Path(template).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "videoid.en.srt").write_text(srt_text, encoding="utf-8")
        return _FakeProc(returncode=returncode)
    return runner


SRT = """\
1
00:00:00,000 --> 00:00:02,000
Hello world

2
00:00:02,000 --> 00:00:04,000
Second line
"""


def test_youtube_with_transcript():
    runner = _make_runner_writing_srt(SRT)
    text, meta, att = url_youtube.extract(
        json.dumps({"url": "https://youtu.be/x"}),
        runner=runner,
    )
    assert "Hello world" in text
    assert "Second line" in text
    assert meta["youtube"] is True
    assert att is None


def test_youtube_no_transcript_permanent():
    def runner(args, capture_output=True, text=True, timeout=None):
        return _FakeProc(returncode=0)
    with pytest.raises(PermanentHandlerError):
        url_youtube.extract(json.dumps({"url": "https://youtu.be/x"}), runner=runner)


def test_youtube_nonzero_exit_transient():
    def runner(args, capture_output=True, text=True, timeout=None):
        return _FakeProc(returncode=1, stderr="oops")
    with pytest.raises(TransientHandlerError):
        url_youtube.extract(json.dumps({"url": "https://youtu.be/x"}), runner=runner)


def test_youtube_timeout_transient():
    def runner(args, **kw):
        raise subprocess.TimeoutExpired(cmd="yt-dlp", timeout=1)
    with pytest.raises(TransientHandlerError):
        url_youtube.extract(json.dumps({"url": "https://youtu.be/x"}), runner=runner)


def test_youtube_missing_binary_transient():
    def runner(args, **kw):
        raise FileNotFoundError("yt-dlp")
    with pytest.raises(TransientHandlerError):
        url_youtube.extract(json.dumps({"url": "https://youtu.be/x"}), runner=runner)


def test_youtube_missing_url():
    with pytest.raises(PermanentHandlerError):
        url_youtube.extract(json.dumps({}))


def test_youtube_empty_srt_permanent():
    runner = _make_runner_writing_srt("")
    with pytest.raises(PermanentHandlerError):
        url_youtube.extract(json.dumps({"url": "https://youtu.be/x"}), runner=runner)
