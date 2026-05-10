"""Test fixtures for the dashboard backend.

Provides:
- A throwaway vault directory with a minimal PARA layout + ``_meta``,
- A throwaway SQLite file with the queue + claude_calls schemas,
- An in-process FastAPI test client wired against the above.
"""
from __future__ import annotations

import sqlite3
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

# Make ``backend`` importable from ``dashboard/`` without an editable install.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.app import create_app  # noqa: E402
from backend.config import Settings  # noqa: E402

TEST_TOKEN = "dashboard-test-token-DO-NOT-USE-IN-PROD"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@pytest.fixture
def vault_dir(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for sub in ("_inbox", "_meta", "_attachments", "projects", "areas",
                "resources", "archive"):
        (vault / sub).mkdir(parents=True, exist_ok=True)
    (vault / "projects" / "memex").mkdir(parents=True, exist_ok=True)
    (vault / "resources" / "ml-papers").mkdir(parents=True, exist_ok=True)
    (vault / "_meta" / "taxonomy.yml").write_text(
        textwrap.dedent(
            """
            schema_version: 1
            default_route: _inbox
            confidence:
              autonomous_threshold: 0.80
              review_threshold: 0.60
            folders:
              - path: projects/memex
                description: "Memex itself."
                keywords: [memex]
                confidence_override: null
              - path: resources/ml-papers
                description: "ML paper notes."
                keywords: [paper, eval]
                confidence_override: null
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return vault


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "memex.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE queue (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at      TEXT    NOT NULL,
            updated_at      TEXT    NOT NULL,
            source_type     TEXT    NOT NULL CHECK (source_type IN ('url','file','text','voice')),
            source_payload  TEXT    NOT NULL,
            submitter       TEXT    NOT NULL,
            status          TEXT    NOT NULL DEFAULT 'queued'
                            CHECK (status IN ('queued','processing','filed','needs_review','failed')),
            attempts        INTEGER NOT NULL DEFAULT 0,
            last_error      TEXT,
            processed_at    TEXT,
            confidence      REAL,
            vault_path      TEXT,
            claude_session_id TEXT,
            claude_input_tokens  INTEGER,
            claude_output_tokens INTEGER,
            claude_duration_ms   INTEGER
        );
        CREATE INDEX queue_status_created_at ON queue (status, created_at);
        CREATE INDEX queue_submitter         ON queue (submitter);
        CREATE TABLE claude_calls (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ts              TEXT    NOT NULL,
            service         TEXT    NOT NULL,
            purpose         TEXT    NOT NULL,
            queue_item_id   INTEGER,
            session_id      TEXT,
            input_tokens    INTEGER,
            output_tokens   INTEGER,
            duration_ms     INTEGER,
            exit_code       INTEGER NOT NULL
        );
        CREATE INDEX claude_calls_ts ON claude_calls (ts);
        """
    )
    conn.close()
    return db


@pytest.fixture
def settings(vault_dir: Path, db_path: Path, tmp_path: Path) -> Settings:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = prompts_dir / "retrieve.md"
    prompt_path.write_text(
        "Vault: {vault_dir}\nQuestion: {question}\n",
        encoding="utf-8",
    )
    return Settings(
        bearer_token=TEST_TOKEN,
        vault_dir=vault_dir,
        db_path=db_path,
        claude_bin="/usr/local/bin/claude-fake",
        claude_timeout_seconds=5.0,
        retrieval_prompt_path=prompt_path,
        frontend_dist_dir=None,
        log_level="ERROR",
        bind_host="127.0.0.1",
        bind_port=0,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def insert_queue_row(db_path: Path):
    """Helper that inserts a row directly and returns its id."""
    def _insert(
        *,
        source_type: str = "url",
        source_payload: str = '{"url":"https://example.com"}',
        submitter: str = "api:test",
        status: str = "queued",
        attempts: int = 0,
        confidence: float | None = None,
        vault_path: str | None = None,
        last_error: str | None = None,
    ) -> int:
        conn = sqlite3.connect(db_path)
        try:
            ts = _utc_now_iso()
            cur = conn.execute(
                "INSERT INTO queue (created_at, updated_at, source_type, source_payload, "
                "submitter, status, attempts, confidence, vault_path, last_error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ts, ts, source_type, source_payload, submitter, status,
                 attempts, confidence, vault_path, last_error),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    return _insert


@pytest.fixture
def insert_claude_call(db_path: Path):
    def _insert(
        *,
        ts: str | None = None,
        service: str = "worker",
        purpose: str = "file",
        exit_code: int = 0,
        input_tokens: int = 100,
        output_tokens: int = 50,
        duration_ms: int = 1500,
        session_id: str | None = "sess-test",
        queue_item_id: int | None = None,
    ) -> int:
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute(
                "INSERT INTO claude_calls (ts, service, purpose, queue_item_id, "
                "session_id, input_tokens, output_tokens, duration_ms, exit_code) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ts or _utc_now_iso(), service, purpose, queue_item_id,
                 session_id, input_tokens, output_tokens, duration_ms, exit_code),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    return _insert
