# memex-worker — Phase 3

The Memex processing worker. Polls the shared SQLite queue, extracts content,
asks `claude -p` where each item belongs, writes a markdown note into the
vault, and updates the queue row.

See `/CLAUDE.md` for the binding system contract. This README only covers
worker-local operational concerns.

## Overview

```
queue (sqlite WAL)
   │  status=queued
   ▼
[claim_batch] → [handler] → [claude_runner] → [vault_writer] → [mark_filed | mark_needs_review | mark_failed]
```

One synchronous loop, no asyncio. Items are claimed atomically with a
status-guarded `UPDATE`, processed serially within a batch, and the tick
sleeps for `MEMEX_WORKER_BATCH_PAUSE_SECONDS` after any non-empty batch —
the system's only built-in Claude-Max throttle, plus the in-memory
`RateLimiter` that adds an extra pause if recent call durations exceed a
window threshold.

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `MEMEX_WORKER_DB_PATH` | `/srv/memex/data/memex.db` | Shared SQLite file. |
| `MEMEX_WORKER_VAULT_DIR` | `/srv/memex/vault` | Vault root. |
| `MEMEX_WORKER_INBOX_DIR` | `/srv/memex/data/uploads` | Capture-API upload root. |
| `MEMEX_WORKER_TAXONOMY_PATH` | `/srv/memex/vault/_meta/taxonomy.yml` | Reloaded every batch. |
| `MEMEX_WORKER_PROMPTS_DIR` | `<pkg>/prompts` | Prompt template root. |
| `MEMEX_WORKER_MIGRATIONS_DIR` | `<pkg>/migrations` | Worker-owned migrations. |
| `MEMEX_WORKER_POLL_SECONDS` | `5` | Idle poll interval. |
| `MEMEX_WORKER_BATCH_MAX` | `10` | Max items claimed per tick. |
| `MEMEX_WORKER_BATCH_PAUSE_SECONDS` | `60` | Pause after a non-empty tick. |
| `MEMEX_WORKER_MAX_ATTEMPTS` | `5` | Retries before terminal `failed`. |
| `MEMEX_WORKER_CLAUDE_BIN` | `claude` | Binary used for `claude -p`. |
| `MEMEX_WORKER_CLAUDE_TIMEOUT_SECONDS` | `180` | Per-call timeout. |
| `MEMEX_WORKER_WHISPER_BIN` | `whisper-cpp` | Whisper binary. |
| `MEMEX_WORKER_WHISPER_MODEL` | `/models/ggml-base.en.bin` | Whisper model file. |
| `MEMEX_WORKER_RATE_LIMIT_WINDOW_SECONDS` | `300` | Rolling-window size. |
| `MEMEX_WORKER_RATE_LIMIT_THRESHOLD_MS` | `180000` | Window total at which to pause. |
| `MEMEX_WORKER_HEALTHCHECK_PATH` | `/tmp/memex-worker.healthy` | Touched each tick. |
| `MEMEX_LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARN`/`ERROR`. |

## Local development

```bash
cd worker
python3 -m venv ../.venv
../.venv/bin/pip install -e '.[dev]'
../.venv/bin/python -m pytest
```

The tests mock all subprocess calls (`claude`, `yt-dlp`, `whisper-cpp`) and
all network access (`trafilatura`). You do not need any of those binaries
installed to run the suite.

## Running tests

```bash
../.venv/bin/python -m pytest                  # full suite + coverage
../.venv/bin/python -m pytest tests/test_main_loop.py -v
```

Coverage gate is `--cov-fail-under=85`; CI must fail if coverage drops.

## Prompt versioning

`worker/prompts/file.md` carries a YAML-comment `prompt_version` header. Any
change that could shift filing decisions (added rules, reworded constraints,
new fields) must bump this version in the same commit. The dashboard's
"recent filing decisions" view can correlate `prompt_version` against
confidence drift over time.

## Whisper model swapping

The Dockerfile builds whisper.cpp from a pinned commit but does not bake a
model. Mount the model file at the path named by `MEMEX_WORKER_WHISPER_MODEL`
(e.g. `/models/ggml-base.en.bin`). To swap models, change the bind mount in
`infra/docker-compose.yml` — no rebuild required. `base.en` is the default;
`tiny.en` is a fallback if the Pi's RAM is squeezed.

## Operational notes

- The worker is the only writer of `status` values other than `queued`.
  Capture API only ever inserts `queued`; the dashboard is strictly read-only.
- On startup, any row stuck in `processing` (process crash, OOM kill) is
  reset to `queued`. See `worker/recovery.py`.
- The `claude_calls` table is shared write surface: bot + dashboard insert
  their own rows with the same shape. The migrations runner is idempotent
  so multiple services can race the first-run DDL safely.
- Permanent handler failures (no transcript, unsupported binary, etc.) end
  up as inbox stubs with `extraction_failed: true` and `status='needs_review'`.
  True terminal failures (`status='failed'`) only happen after `max_attempts`
  transient errors.
- Notes are written via write-temp → fsync → rename → fsync-directory, so a
  mid-write crash never leaves a half-formed file at the canonical path.
