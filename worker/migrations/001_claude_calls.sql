-- Phase 3 — claude_calls telemetry table per CLAUDE.md "Rate-limit accounting".
-- Lives in the same SQLite file as the queue; ownership is the worker, but the
-- bot and the dashboard write rows for their own claude -p invocations too.

CREATE TABLE IF NOT EXISTS claude_calls (
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

CREATE INDEX IF NOT EXISTS claude_calls_ts ON claude_calls (ts);
