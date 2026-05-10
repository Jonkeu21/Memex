-- Phase 2 — initial schema. Mirrors the queue DDL in CLAUDE.md.
-- The shared SQLite database also receives writes from the worker (Phase 3)
-- and reads from the dashboard (Phase 6). Schema names are normative.

CREATE TABLE IF NOT EXISTS queue (
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

CREATE INDEX IF NOT EXISTS queue_status_created_at ON queue (status, created_at);
CREATE INDEX IF NOT EXISTS queue_submitter         ON queue (submitter);
