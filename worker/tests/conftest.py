"""Shared test fixtures."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from worker.config import Settings
from worker.db import connect, install_queue_schema, insert_queue_row, apply_migrations


_TAXONOMY_YAML = """\
schema_version: 1
default_route: _inbox
confidence:
  autonomous_threshold: 0.80
  review_threshold: 0.60
folders:
  - path: projects/memex
    description: "Memex build."
    keywords: [memex, raspberry pi, claude]
    confidence_override: null
  - path: areas/health
    description: "Health logs."
    keywords: [sleep, hrv]
    confidence_override:
      autonomous_threshold: 0.85
      review_threshold: 0.65
  - path: resources/ml-papers
    description: "ML papers."
    keywords: [transformer, paper]
    confidence_override: null
"""


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "_inbox").mkdir(parents=True)
    (vault / "_attachments").mkdir(parents=True)
    (vault / "_meta").mkdir(parents=True)
    (vault / "projects" / "memex").mkdir(parents=True)
    (vault / "areas" / "health").mkdir(parents=True)
    (vault / "resources" / "ml-papers").mkdir(parents=True)
    (vault / "_meta" / "taxonomy.yml").write_text(_TAXONOMY_YAML, encoding="utf-8")
    return vault


@pytest.fixture
def taxonomy_yaml() -> str:
    return _TAXONOMY_YAML


@pytest.fixture
def tmp_db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "memex.db"
    conn = connect(db_path)
    install_queue_schema(conn)
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    apply_migrations(conn, migrations_dir)
    return conn


@pytest.fixture
def settings(tmp_path: Path, tmp_vault: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "memex.db",
        vault_dir=tmp_vault,
        inbox_dir=tmp_path / "uploads",
        taxonomy_path=tmp_vault / "_meta" / "taxonomy.yml",
        migrations_dir=Path(__file__).resolve().parent.parent / "migrations",
        prompts_dir=Path(__file__).resolve().parent.parent / "prompts",
        poll_seconds=0.01,
        batch_max=10,
        batch_pause_seconds=0.0,
        max_attempts=5,
        claude_bin="claude",
        claude_timeout_seconds=10.0,
        whisper_bin="whisper-cpp",
        whisper_model=tmp_path / "model.bin",
        rate_limit_window_seconds=300.0,
        rate_limit_threshold_ms=180_000,
        healthcheck_path=tmp_path / "health",
        log_level="INFO",
    )


@pytest.fixture
def insert_url():
    def _make(conn: sqlite3.Connection, url: str = "https://example.com/post", note: str = "") -> int:
        payload = {"url": url, "user_note": note}
        return insert_queue_row(conn, source_type="url", source_payload=json.dumps(payload), submitter="api:telegram")
    return _make


@pytest.fixture
def insert_text():
    def _make(conn: sqlite3.Connection, text: str = "hello world") -> int:
        return insert_queue_row(conn, source_type="text", source_payload=json.dumps({"text": text}), submitter="api:telegram")
    return _make


@pytest.fixture
def insert_file():
    def _make(conn: sqlite3.Connection, *, stored_path: str, mime_type: str, original_filename: str = "f", size_bytes: int = 0) -> int:
        payload = {
            "original_filename": original_filename,
            "stored_path": stored_path,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
        }
        return insert_queue_row(conn, source_type="file", source_payload=json.dumps(payload), submitter="api:telegram")
    return _make


@pytest.fixture
def insert_voice():
    def _make(conn: sqlite3.Connection, *, stored_path: str) -> int:
        payload = {
            "original_filename": "voice.ogg",
            "stored_path": stored_path,
            "mime_type": "audio/ogg",
            "size_bytes": 1234,
            "duration_seconds": 5.0,
        }
        return insert_queue_row(conn, source_type="voice", source_payload=json.dumps(payload), submitter="api:telegram")
    return _make


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.t = start

    def monotonic(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


def make_envelope(folder: str, title: str, summary: str = "summary", tags=None, confidence: float = 0.9) -> dict:
    inner = {
        "folder": folder,
        "title": title,
        "summary": summary,
        "tags": tags or [],
        "confidence": confidence,
    }
    return {
        "session_id": "sess-1",
        "result": json.dumps(inner),
        "input_tokens": 100,
        "output_tokens": 50,
    }


class FakeCompletedProcess:
    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


@pytest.fixture
def claude_envelope_factory():
    def _factory(folder: str = "resources/ml-papers", title: str = "Note title",
                 summary: str = "A summary.", tags=None, confidence: float = 0.9) -> str:
        return json.dumps(make_envelope(folder, title, summary, tags, confidence))
    return _factory


@pytest.fixture
def fixed_now():
    return datetime(2026, 5, 10, 14, 22, 1, 123456, tzinfo=timezone.utc)
