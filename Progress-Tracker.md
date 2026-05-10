# Progress-Tracker.md — Memex cross-session lab notebook

## Purpose

This file is the project's lab notebook. Every Claude Code session that touches this repo reads it before writing code so it knows what previous phases actually built, what they deferred, what they decided that isn't already in `CLAUDE.md`, and what surprised them. It is the only durable record of project state besides the code itself and `CLAUDE.md`.

## How to use it

1. **Read top-down chronologically.** Phase 1 is the oldest entry; the last entry under this header is the most recent state of the world.
2. **Append, never edit.** Earlier entries are immutable history. If a previous decision was wrong, write a new entry describing the reversal — do not rewrite the original.
3. **Spec vs notebook.** `CLAUDE.md` is the normative spec: schemas, names, thresholds, contracts. This file is narrative: choices, trade-offs, deferrals, surprises, and notes for the next session. If a fact belongs in both places, put it in `CLAUDE.md` and reference it here.
4. **Dates are real dates.** If the runtime date is not in your context, ask the operator. Never guess. ISO-8601, `YYYY-MM-DD`.
5. **One entry per phase.** A phase that spans multiple sessions still gets a single entry, written when the phase is declared complete.

## Entry template

Every later entry must follow this schema. Copy the block, fill in every field, and append it under the most recent entry.

```markdown
## Phase N — <name>

**Date completed:** YYYY-MM-DD   <!-- ask the operator if not in context; never guess -->
**Session model:** <e.g. "Claude Opus 4.7 (1M context)" if known; otherwise "unknown">

### What was built
- `path/to/file` — one-line purpose.
- `path/to/other/file` — one-line purpose.

### Key decisions made (and why)
- Decision, in one sentence. Rationale, in one sentence. Only list decisions baked into code that future phases need to know but that are NOT already in `CLAUDE.md`.

### Deviations from the prompt spec
- None. <!-- or: a bullet list of deviations with rationale -->

### Deferred / left for later phases
- What was left undone, who picks it up, why it was deferred.

### Open questions / known issues
- Anything the next phase should know about but doesn't have a clear answer for.

### Test status
- What is covered, what passes, what is flaky or skipped and why.

### Notes for the next phase
- Anything subtle that won't be obvious from reading the code.
```

---

## Phase 1 — Architecture & contracts document

**Date completed:** 2026-05-10
**Session model:** Claude Opus 4.7 (1M context)

### What was built
- `CLAUDE.md` — the binding contract for every component: system overview, repo layout, vault layout, taxonomy file format, queue DDL, capture API surface, worker contract, Telegram bot contract, retrieval response schema, confidence thresholds, logging rules, rate-limit accounting, front-matter schema, and a `contract_version` change-control rule.
- `Progress-Tracker.md` — this file: header, append-only rule, entry template, and this first entry.

### Key decisions made (and why)
- Picked **YAML** over TOML for `taxonomy.yml`. YAML reads cleanly with nested keyword lists and per-folder override blocks, and the operator already authors YAML in Obsidian front-matter, so there's no second syntax to learn.
- Picked **structured JSON** over freeform markdown for the `claude -p` retrieval response (`answer`, `sources[]`, `quotes[]`, `confidence`). Freeform output makes Telegram chunking and dashboard chip rendering ambiguous; JSON gives both renderers the same fields and lets us truncate quotes deterministically.
- Picked **PARA** as the default taxonomy. It's small (4 buckets), well-known, and the `_inbox/` overflow folder absorbs the misfits — this avoids endlessly debating folder ontology and lets the operator evolve it via `taxonomy.yml`.
- Picked **two confidence thresholds, three bands** (`autonomous`, `review`, `inbox`) over a single threshold. A binary cutoff makes the system feel either trigger-happy or useless near the boundary; the middle band lets borderline notes land in their best-guess folder with a `needs_review: true` flag, which the dashboard can surface separately.
- Picked **a polling worker** (5 s tick + 60 s pause between non-empty ticks) over an event-driven design. SQLite + polling is dead simple to operate on a Pi, and the pause is the only Claude-Max throttle the system actually needs given single-user load.
- Picked **plural-noun resource paths** (`/captures/url`) over verb paths (`/capture-url`). Consistency with REST norms; the dashboard backend will reuse the same router prefix.
- Picked **bind-mounted SQLite** at `/srv/memex/data/memex.db` shared by capture API, worker, and dashboard, with WAL mode. A single file is the simplest possible queue substrate, and WAL handles the modest concurrency.
- Picked **stateless Telegram bot** that does not subscribe to queue completion events. The user finds out where things landed via `/last` or the dashboard. This keeps the bot trivially restartable and avoids a second async loop in the bot process.
- Picked **first-match-wins ordered intent rules** over a classifier. Six rules, deterministic, debuggable from a single message; a reviewer can trace any inbound message to its intent in their head.

### Deviations from the prompt spec
- None.

### Deferred / left for later phases
- The `shared/memex_shared/` package is referenced by `CLAUDE.md` (taxonomy loader, frontmatter writer, structured logger, claude wrapper) but not yet implemented. Phase 2 should create it as part of standing up the capture API, since the API needs the queue DDL helpers and the structured logger immediately.
- Prompt files (`worker/prompts/file.md`, `telegram_bot/prompts/retrieve.md`) are not authored. Phase 3 (worker) and Phase 4 (bot) author their respective prompts, constrained to produce the JSON schemas in `CLAUDE.md`.
- Compose orchestration, Tailscale config, and Syncthing config are Phase 5; nothing to write yet.
- The dashboard's frontend (Minimal UI Kit / React) is Phase 6.

### Open questions / known issues
- The capture API's max upload size is set to **25 MB** in the contract. This is a guess based on Telegram's bot-API file ceiling (20 MB inbound) plus headroom for direct uploads from the dashboard. If Phase 4 finds Telegram's effective ceiling is lower in practice, the bot should reject before forwarding rather than relying on the API to 413.
- The `claude_calls` telemetry table assumes `claude -p --output-format json` returns a `session_id` and token counts in its envelope. If that envelope shape differs in the installed CLI version, Phase 3 should record what the wrapper actually sees and either adapt the parser or drop the unavailable columns to NULL — but it must not change the column names without bumping `contract_version`.
- Whisper.cpp model choice is left to Phase 3. The contract says "tiny / base"; on a 4 GB Pi 5, base.en is the safe default but tiny.en may be necessary if the worker shares RAM with the dashboard.

### Test status
- No tests. The artifact is the contract document itself. Self-checked against the seven acceptance criteria in the Phase 1 prompt: a reviewer can write the queue DDL, implement `POST /captures/url`, hand-author `taxonomy.yml`, predict intent for any Telegram message, render the retrieval payload in both UIs, route by confidence band, and parse a structured log line — all from `CLAUDE.md` alone.

### Notes for the next phase
- Treat the names in `CLAUDE.md` as **binding**: column names, endpoint paths, enum values, log event names, env var names. If Phase 2 needs a name that isn't in `CLAUDE.md`, add it to `CLAUDE.md` (patch bump) in the same PR.
- The `submitter` column is `'telegram:<chat_id>'` or `'api:<token_label>'`. The Telegram bot calls the capture API with the `telegram` token, so its rows will land as `submitter = 'api:telegram'` — there is intentionally no second submitter format for bot-originated captures, because the bot has no privileged path into the queue. If Phase 2 or 4 disagrees, raise it before implementing.
- `contract_version` starts at `1.0.0`. Bump to `1.0.1` for prose-only edits (typos, clarifications), `1.1.0` for additive schema changes (new optional field, new endpoint), `2.0.0` only for true breaks.

---

## Phase 2 — Capture API

**Date completed:** 2026-05-10
**Session model:** Claude Opus 4.7 (1M context)

### What was built
- `capture_api/app/main.py` — FastAPI app factory, lifespan that opens the SQLite connection and runs migrations, request-scoped JSON access log middleware.
- `capture_api/app/config.py` — env-var loader with validation; `MEMEX_CAPTURE_TOKEN_<LABEL>` discovery, port/upload/log-level checks.
- `capture_api/app/auth.py` — bearer-token dependency with constant-time comparison over every configured token (timing depends on token-set size, not match position).
- `capture_api/app/db.py` — `sqlite3` connection helper (WAL mode), forward-only migrations runner that records applied filenames in `_migrations`, `is_writable` probe for `/readyz`, module-level `WRITE_LOCK`.
- `capture_api/app/logging.py` — JSON-to-stdout formatter with secret-key regex redaction, body-size substitution for `text`/`body`/`content`, chat-id hashing.
- `capture_api/app/files.py` — filename sanitiser (rejects `..`, path separators, null bytes; strips leading dots; caps to 200 chars), streaming uploader to a `.part` file with size cap and atomic `os.replace` commit/discard semantics.
- `capture_api/app/schemas.py` — pydantic v2 request/response models (`UrlCapture`, `TextCapture`, `CaptureAck`, `QueueItem`, `QueueListing`).
- `capture_api/app/routes/capture.py` — `POST /captures/{url,text,file,voice}`, all 202 with `{id,status:'queued',created_at}`. File/voice stream → DB insert (under `WRITE_LOCK` using `RETURNING id`) → file rename atomically.
- `capture_api/app/routes/queue.py` — `GET /captures` (cursor-based newest-first listing with `status`/`source_type` filters) and `GET /captures/{id}` (404 with the contract's error envelope on miss).
- `capture_api/app/routes/health.py` — `GET /healthz` (open) and `GET /readyz` (auth-gated; 503 if SQLite write probe fails).
- `capture_api/app/migrations/001_initial.sql` — queue table + indexes mirroring CLAUDE.md DDL byte-for-byte.
- `capture_api/tests/` — eleven test modules covering auth, each capture endpoint, queue listing/single, health/readyz, migrations idempotency, file/logging units, and a 50-way concurrent text-capture smoke test. 61 tests, 94% coverage on `app/`.
- `capture_api/Dockerfile` — multi-stage, slim Python 3.11 base, non-root `memex` user, `/data/inbox` and `/data/queue.db` defaults, `/healthz` healthcheck, factory-mode uvicorn.
- `capture_api/pyproject.toml`, `capture_api/.dockerignore`, `capture_api/README.md`.

### Key decisions made (and why)
- Resolved several prompt-vs-`CLAUDE.md` collisions in `CLAUDE.md`'s favour, because Phase 1's contract is binding. Specifically: endpoint paths are `/captures/...` (plural), the listing path is `GET /captures` with cursor pagination (not `GET /queue` with offset/limit), and the queue status enum stays `queued` (not the prompt's `pending`). The `submitter` column is populated as `api:<label>`, where `<label>` is the suffix on the matched `MEMEX_CAPTURE_TOKEN_<LABEL>` env var.
- Used `MEMEX_CAPTURE_TOKEN_<LABEL>=<value>` env vars for tokens (multi-token, label-tagged) instead of the prompt's single `CAPTURE_API_TOKEN`. This is what `CLAUDE.md` mandates and is also necessary to populate the `submitter` column meaningfully.
- Took the module-level `WRITE_LOCK` and `INSERT … RETURNING id` rather than a connection-per-request pool. FastAPI's sync routes run in a threadpool that can race on a shared `sqlite3.Connection`'s `last_insert_rowid()`; serialising writes is cheap on a single-user system and keeps the runtime model identical between the worker (single-threaded asyncio) and the API.
- Chose cursor-based pagination (`?cursor=<id>&limit=N`, response `{items, next_cursor}`) over offset/limit because that's what `CLAUDE.md`'s example response shows and it stays correct as new rows arrive at the head while the dashboard pages.
- Filename sanitiser **rejects** any name containing `..` or null bytes (raising 400) but only **strips** path separators (taking the basename). This is the explicit prompt rule; a previous draft tried to silently sanitise `..` and was reversed when the `reject ..` test case exposed it.
- `app/logging.py` lives inside `capture_api/` rather than in `shared/memex_shared/`. Phase 1's tracker noted that the shared package was deferred to Phase 2; rather than build a half-populated `shared/` and risk diverging from later phases' needs, we kept the structured logger local. Phase 3 (worker) and Phase 6 (dashboard) should extract it to `shared/memex_shared/logging.py` when they need to import it — the public API (`configure`, `log_event`, `redact`, `hash_chat_id`, `JsonFormatter`) is small and stable.
- The migration runner runs each `.sql` file via `executescript` *outside* an explicit `BEGIN/COMMIT`, because `executescript` commits any open transaction implicitly in Python's `sqlite3` autocommit mode. Migration files use idempotent DDL (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`) so a partial-failure retry on the next startup is safe.

### Deviations from the prompt spec
- Endpoint paths, listing path, status enum, pagination shape, and token env-var naming follow `CLAUDE.md` rather than the prompt — see "Key decisions" above. The prompt itself states `CLAUDE.md` is binding when the two disagree, so this is the prescribed resolution rather than a deviation, but it is worth flagging here for anyone reading the prompt cold.
- `app/logging.py` is in `capture_api/app/` not `shared/memex_shared/` — see above.

### Deferred / left for later phases
- `shared/memex_shared/` package extraction. Phase 3 (worker) is the natural moment: it needs `logging.py` and the queue DDL helpers. The current capture_api copy is the canonical implementation until then.
- Worker, Telegram bot, dashboard, Compose, Tailscale, Syncthing — all untouched.
- The capture API does **not** validate that the `submitter` token label `telegram` exists at startup; the bot will produce `submitter='api:telegram'` by configuring `MEMEX_CAPTURE_TOKEN_telegram=...`. Phase 4 may want a startup probe that confirms its token is accepted before the bot starts polling Telegram.

### Open questions / known issues
- The 25 MB upload ceiling (CLAUDE.md) maps cleanly onto `CAPTURE_MAX_UPLOAD_MB=25`. Tests exercise it at 1 MB. If Phase 4 needs to forward Telegram's 20 MB inbound files plus a wrapper, headroom is tight; revisit if compose-time uploads regularly hit 413.
- WAL mode requires the SQLite file to live on a filesystem that supports `mmap` and locking. The Pi's bind-mounted `/srv/memex/data/` is local ext4 so this is fine, but moving the queue file to NFS would silently degrade.
- `/readyz` currently writes a tiny probe table (`_readyz_probe`); it's harmless but it does create one extra SQL table in the shared DB. The worker and dashboard should ignore it.

### Test status
- 61 tests, all passing. Coverage on `app/` is **94.14 %** (gate is 90 %).
- Includes a 50-way concurrent text-capture test that uncovered the `lastrowid` race; documented above.
- Skipped: none. Flaky: none observed across local runs.

### Notes for the next phase
- The worker is the only component that may write to `status IN ('processing','filed','needs_review','failed')`. The capture API's INSERT hard-codes `'queued'`. Don't relax that.
- `request.state.queue_item_id` is set inside each capture handler so the access-log middleware can include it. If Phase 6 reuses this router prefix from inside the dashboard backend, set the same attribute when emitting access logs there.
- The error envelope for 404 / 401 / 413 is `{"detail": {"error": {"code": ..., "message": ...}}}` — this is the FastAPI `HTTPException(detail=...)` shape. The 422 envelope is FastAPI's standard `{"detail": [...]}` per the prompt's instruction. Future error responses should follow whichever shape matches the response code's existing tests rather than introducing a third.
