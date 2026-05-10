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

---

## Phase 3 — Processing worker

**Date completed:** 2026-05-10
**Session model:** Claude Opus 4.7 (1M context)

### What was built
- `worker/worker/main.py` — synchronous main loop: claim batch, dispatch handler, drive `claude -p`, route by confidence, write note, update queue row. `_process_row` is the single per-item path; `_write_inbox_stub` handles permanent extraction failures; `_retry_or_fail` applies the `max_attempts` policy.
- `worker/worker/config.py` — env-driven `Settings` dataclass with `MEMEX_WORKER_` prefix and explicit min/max validation.
- `worker/worker/db.py` — connection helper (WAL, busy_timeout), migration runner, `claim_batch` with status-guarded `UPDATE`, status transition helpers (`mark_filed`/`mark_needs_review`/`mark_failed`/`release_for_retry`), `record_claude_call`, plus a `install_queue_schema` test seam so tests don't depend on `capture_api/`.
- `worker/worker/taxonomy.py` — YAML loader + validator + `resolve_thresholds` (per-folder override aware). No caching: the main loop reloads on every batch per the contract.
- `worker/worker/claude_runner.py` — subprocess wrapper, prompt-template substitution, envelope/inner-JSON parser, type-and-range validator. Distinct exception classes (`ClaudeTransientError`, `ClaudeMalformedJSONError`, `ClaudeValidationError`) drive the retry policy.
- `worker/worker/vault_writer.py` — `slugify`, `build_filename` with `-2`/`-3` collision suffixes, `atomic_write` with a `crash_after_temp` test seam, `build_front_matter` enforcing the strict CLAUDE.md field order, `render_note` producing the `H1 → summary → ## Source → body` body shape.
- `worker/worker/handlers/{text,url_article,url_youtube,voice,file}.py` — per-source-type extractors with a uniform return shape `(extracted_text, source_metadata, attachment_relpath)`. `url_article` dispatches to `url_youtube` for YouTube hosts (per CLAUDE.md, YouTube is not a separate `source_type`).
- `worker/worker/rate_limit.py` — in-memory rolling-window `RateLimiter` with injectable clock; trips an extra `window/4` pause when recent claude durations exceed the threshold.
- `worker/worker/recovery.py` — `reset_stuck_processing` flips any `status='processing'` rows back to `queued` on startup.
- `worker/worker/logging.py` — JSON logger adapted from `capture_api/app/logging.py` with `service="worker"`; same `redact` + `hash_chat_id` surface.
- `worker/prompts/file.md` — versioned prompt template (`prompt_version: 1`) with the four substitution slots and the exact JSON shape the runner expects back.
- `worker/migrations/001_claude_calls.sql` — `claude_calls` telemetry table per CLAUDE.md.
- `worker/tests/*` — 126 tests across 14 files, mocking all subprocess + network paths. Coverage 90.69% (gate 85%).
- `worker/Dockerfile`, `worker/.dockerignore`, `worker/pyproject.toml`, `worker/README.md`.

### Key decisions made (and why)
- **Prompt template lives in `worker/prompts/file.md` and is versioned via a YAML-comment header (`prompt_version: 1`)**. Versioned in the file rather than the code path so changes are reviewable on their own; the dashboard can correlate `prompt_version` against filing-decision drift later.
- **Three distinct claude-failure exception classes** (`ClaudeTransientError`, `ClaudeMalformedJSONError`, `ClaudeValidationError`). All currently treated as transient by the retry policy, but the separation lets the dashboard surface "model returned bad JSON" vs "model couldn't be reached" without re-parsing `last_error` strings.
- **Permanent extraction failures end up as `status='needs_review'` with `extraction_failed: true` in front-matter**, not `status='failed'`. The contract says "route to `_inbox/` with `extraction_failed: true`" — that is a successful inbox placement that the operator can triage, not a terminal failure. `status='failed'` is reserved for transient errors that exhausted `max_attempts`.
- **YouTube dispatched from inside `handlers/url_article.py`**, not a separate `source_type`. CLAUDE.md only lists four source types; the URL handler classifies by host and tail-calls `url_youtube.extract`. This keeps the queue's `CHECK` constraint stable.
- **Single-threaded synchronous loop**, not asyncio. The bottleneck is the serial `claude -p` subprocess; coroutines add complexity with no throughput win.
- **Taxonomy reloaded per batch**, no mtime caching. The contract is explicit ("no caching across calls") and the cost is a small YAML parse — trivial next to a model call.
- **In-memory `RateLimiter` rather than a DB-backed window query**. The rate-limit gate is advisory and per-process; the `claude_calls` table is the durable record. Two stores, two readers, no mutex.
- **`atomic_write` accepts a `crash_after_temp` test seam** rather than monkey-patching `os.replace`. The seam is documented and the test verifies the canonical path is never created when the seam fires.
- **`install_queue_schema` lives next to the worker's own migrations** so the test suite can construct a queue table without taking a dev dep on `capture_api/`. The DDL is copied verbatim from `CLAUDE.md`; if either side drifts, the contract is the tie-breaker.
- **`MEMEX_WORKER_` prefix on every worker env var** to match CLAUDE.md's named example (`MEMEX_WORKER_BATCH_PAUSE_SECONDS`). The log-level variable stays `MEMEX_LOG_LEVEL` (cross-cutting).
- **YAML scalar quoting is intentionally narrow**: only quote when the unquoted form would mis-parse (leading flow indicator, embedded `: `, etc.). The CLAUDE.md example shows `original_url: https://example.com/x` unquoted, and the tests pin that exact form.

### Deviations from the prompt spec
- The original Phase-3 prompt named statuses `pending`/`done`, listed `youtube` as a fifth `source_type`, used `{taxonomy_path, body}` for the `claude -p` JSON, said 30 s poll cycle and max-attempts 3, and called the prompt file `process_item.md`. Followed CLAUDE.md instead per Phase 2 precedent: statuses are `queued|processing|filed|needs_review|failed`, source types are `url|file|text|voice`, the inner JSON is `{folder,title,summary,tags,confidence}`, poll is 5 s + 60 s pause, max-attempts is 5, prompt is `prompts/file.md`. This is documented at the top of the Phase-3 brief.
- `shared/memex_shared/` is still not extracted; both `capture_api/app/logging.py` and `worker/worker/logging.py` carry near-identical implementations. Deferred to a later phase, per Phase 2.

### Deferred / left for later phases
- `shared/memex_shared/` extraction (taxonomy loader, frontmatter writer, structured logger, claude wrapper). Phase 5 or whenever a third service starts duplicating one of these.
- Compose wiring: the worker's `claude` binary, vault bind mount, and whisper model mount are all configured at run-time but not yet declared in `infra/docker-compose.yml`. Phase 5.
- The worker does not notify the Telegram bot when an item moves out of `queued` — by contract the bot is stateless and surfaces results via `/last` or the dashboard. Phase 4 reaffirms this.
- No vault-side cleanup of orphaned `.tmp` files. If a process crashes between temp-write and rename, the temp file is left for an operator (or a Phase 6 dashboard task) to sweep.

### Open questions / known issues
- The real `claude -p --output-format json` envelope shape is assumed (`{session_id, result, input_tokens, output_tokens}` plus an optional `usage: {...}` nest). If the installed CLI emits a different shape, only `claude_runner._parse_envelope` needs to adapt — the contract requires the inner JSON shape, not the envelope.
- Whisper.cpp is built from `v1.7.2` in the Dockerfile. If that tag is gone by the time Phase 5 builds an image, bump the `WHISPER_COMMIT` build arg; the runtime contract is just `whisper-cpp -m <model> -f <audio> -otxt`.
- The rate-limit gate (`window/4` extra pause when recent durations exceed threshold) is a guess. We'll see real numbers once the worker runs on the Pi for a week; the constants are env-tunable and not in the contract.

### Test status
- `python -m pytest` → 126 passed, coverage 90.69% (gate is 85%).
- Every subprocess and network call is mocked. `trafilatura` is mocked by replacing the module in `sys.modules` from the test; `yt-dlp`/`whisper-cpp` are mocked by passing a fake runner callable; `claude -p` is mocked by monkeypatching `claude_runner.invoke`.
- The atomic-write crash seam test confirms the canonical path is absent after a simulated mid-write crash, even though a `.tmp` is left behind.
- Coverage gaps that remain are mostly defensive branches (subprocess-import-failed paths, file/voice handler errors that double-fault).

### Notes for the next phase
- Phase 4 (Telegram bot) can copy `worker/worker/logging.py` verbatim (change `SERVICE_NAME`) until the shared package is extracted.
- The retrieval prompt the bot ships in `telegram_bot/prompts/retrieve.md` should mirror the same structural pattern as `worker/prompts/file.md`: YAML-comment `prompt_version` header, explicit JSON schema with types, and ONLY-JSON instruction.
- The `claude_calls` table is shared write surface; the bot must `INSERT` rows with `service='telegram_bot'`, `purpose='retrieve'`, and `queue_item_id=NULL`. Same nine columns, idempotent migration — `apply_migrations` in `worker/worker/db.py` will be a no-op for already-applied files.
- `worker/worker/db.py::insert_queue_row` is a test helper; production capture comes from `capture_api`. Don't import it from non-test code.
- The contract's "60 s pause between non-empty ticks" is implemented with `time.sleep(BATCH_PAUSE_SECONDS)`. Tests set this to `0.0` via the `Settings` fixture; production picks up the default 60 from `MEMEX_WORKER_BATCH_PAUSE_SECONDS`.

---

## Phase 4 — Telegram bot

**Date completed:** 2026-05-10
**Session model:** Claude Opus 4.7 (1M context)

### What was built
- `telegram_bot/bot/config.py` — env-driven `Settings` dataclass; validates the bot token, the chat-id whitelist, the capture-API base URL/token, and timeouts.
- `telegram_bot/bot/logging.py` — JSON-to-stdout logger with `service="telegram_bot"`; redacts secret-named keys, hashes chat IDs, body-substitutes message text/answer payloads. Adapted from `worker/worker/logging.py` per the Phase 3 hand-off.
- `telegram_bot/bot/auth.py` — chat-ID whitelist check + silent-rejection log helper.
- `telegram_bot/bot/intent.py` — pure-function intent dispatcher implementing CLAUDE.md's six ordered rules; one `Decision` dataclass per intent; rule 3 extracts URL + remnant `user_note`.
- `telegram_bot/bot/capture_client.py` — async `httpx` wrapper for the capture API; one method per endpoint; raises `CaptureAPIError` on any non-2xx so handlers render uniformly.
- `telegram_bot/bot/claude_runner.py` — subprocess wrapper for `claude -p --output-format json`; parses both envelope shapes (`result`-string and `result`-dict); validates the inner retrieval JSON; truncates quotes to 280 chars; distinct `ClaudeTimeoutError`/`ClaudeTransientError`/`ClaudeMalformedJSONError` classes drive the user-facing error rendering.
- `telegram_bot/bot/rendering.py` — three-message renderer (answer / sources / quotes) per CLAUDE.md; chunks answer at paragraph boundaries with `(i/n)` numbering when the body exceeds 3500 chars; explicitly tracks open code-fence parity so a long fenced block is never split mid-fence; appends the `_No sources found in vault._` marker only on the final answer chunk.
- `telegram_bot/bot/downloads.py` — in-memory Telegram download with declared-size and post-download size enforcement; never persists payloads to disk.
- `telegram_bot/bot/queue_reader.py` — read-only SQLite (`mode=ro`) helpers for `/queue` (24-hour status counts) and `/last` (5 most recent rows).
- `telegram_bot/bot/telemetry.py` — appends one row to `claude_calls` per retrieval with `service='telegram_bot'`, `purpose='retrieve'`, `queue_item_id=NULL`; swallows insert failures so telemetry can never crash the bot.
- `telegram_bot/bot/handlers/{capture_url,capture_text,capture_attachment,retrieval,commands}.py` — one module per intent path. Capture handlers reply with `reply_to_message_id`; retrieval replies are plain (no quote of the question).
- `telegram_bot/bot/main.py` — async entry point: chat whitelist, intent dispatcher, command bindings, `Application.builder()` wiring, long-polling startup. `claude -p` runs inside `asyncio.to_thread` so the event loop is never blocked.
- `telegram_bot/prompts/retrieve.md` — `prompt_version: 1`; instructs the model to return ONLY the CLAUDE.md retrieval JSON envelope, with a complete schema example and verbatim-quote/280-char rules.
- `telegram_bot/tests/*` — 11 test modules, 110 tests, **87.57 % coverage on `bot/`** (gate is 85 %).
- `telegram_bot/Dockerfile` — Python 3.11-slim, `linux/arm64`-friendly. The Claude Code CLI is mounted from the host at runtime; not bundled.
- `telegram_bot/pyproject.toml`, `telegram_bot/.dockerignore`, `telegram_bot/README.md`.

### Key decisions made (and why)
- **Followed `CLAUDE.md` over the Phase-4 prompt wherever they disagreed.** Specifically: commands are `/start /help /queue /last /find /capture` (not `/status /inbox /save /cancel`); intent rules are six (not eight) with all attachment kinds unified into rule 1; capture endpoints are plural (`/captures/voice`, not `/capture/voice`); rendering is three separate messages per CLAUDE.md (not one chunked message); chunking happens at 3500 chars with `(i/n)` numbering. Phase 2 set the precedent that CLAUDE.md is binding when the prompt and the contract disagree.
- **Env-var prefix `MEMEX_TELEGRAM_*`** to match CLAUDE.md's named example `MEMEX_TELEGRAM_ALLOWED_CHAT_IDS` and the worker's `MEMEX_WORKER_*` convention. The capture-API token env var is `MEMEX_CAPTURE_API_TOKEN` (the bot doesn't know about labels — it just holds the token value that the API will recognise as `submitter='api:telegram'`).
- **Default `MEMEX_CAPTURE_API_BASE_URL=http://capture_api:8001`** matches the port Phase 2 actually settled on (CLAUDE.md's prose example said 8000; Phase 2's `CAPTURE_BIND_PORT=8001` is the operational reality).
- **Telegram payloads are downloaded to memory, never to disk.** The prompt asked for `tempfile.NamedTemporaryFile`, but going straight to bytes → multipart removes a class of cleanup bugs (no `try/finally` race, no leftover `.tmp` files). The 25 MB download cap is enforced both before (declared `file_size`) and after (actual buffer length) the download.
- **`/queue` and `/last` read SQLite directly via `mode=ro` URI**, instead of fan-out over `GET /captures?status=...`. The dashboard already does the same, the bind mount already exists, and the `MEMEX_TELEGRAM_DB_PATH` env var points at the same file.
- **`claude_calls` insertion is best-effort**: a missing DB or schema-not-yet-applied logs a warning and returns silently. This lets the bot run before the worker has applied its migrations on first boot, and means a corrupted DB doesn't take down retrievals.
- **Code-fence-aware chunker.** The renderer parses each candidate chunk for an odd number of triple-backtick lines; if the count is odd, the next paragraph is appended rather than starting a new chunk. This guarantees a multi-paragraph fenced code block is never split mid-fence, even if it pushes a chunk above the 3500-char target (Telegram's hard cap is 4096; tests assert the produced chunks stay under it).
- **No `python-telegram-bot` testing harness; bespoke fakes.** `FakeMessage`/`FakeChat`/`FakeBot`/`FakeUpdate` dataclasses live in `tests/conftest.py`. They give the test suite full control over attachment shapes and download bytes without spinning up a real `Application`. The trade-off is that we don't exercise PTB's filter logic; covered by the smoke step in §3 of the prompt's acceptance criteria when the bot runs against a real chat.
- **Bot does not retry capture-API calls.** Per the prompt and consistent with the queue's deduplication-via-content model, the user resends if needed; double-captures are worse than dropped ones.

### Deviations from the prompt spec
- **Command set, intent ruleset, endpoint paths, rendering shape, and chunk size**: followed `CLAUDE.md` rather than the prompt — see "Key decisions" above. The prompt itself names CLAUDE.md as binding when the two disagree.
- **Env-var names** are `MEMEX_TELEGRAM_*` not the prompt's bare `TELEGRAM_*`. Reason: matches CLAUDE.md (`MEMEX_TELEGRAM_ALLOWED_CHAT_IDS`) and the worker's prefix convention.
- **Default capture API port is 8001** not 8000 (matches Phase 2's bind port).
- **Telegram downloads are in-memory** not `tempfile.NamedTemporaryFile`. See above.
- **`shared/memex_shared/` extraction is still deferred.** Three services now carry near-identical `logging.py` (capture API, worker, bot) and two carry the queue DDL. Phase 5 (Compose) is the natural moment to extract since Compose has to know which packages each service depends on; deferring further would force a fourth copy in the dashboard.

### Deferred / left for later phases
- `shared/memex_shared/` package extraction (logger, retrieval-envelope dataclasses, claude wrapper). Phase 5 or 6.
- The bot does not subscribe to queue events for "your capture was filed" notifications — by contract it is stateless. The user finds out via `/last` or the dashboard. Phase 6 (dashboard) provides the durable surface.
- Compose wiring of the bot service: bind mounts (`/vault`, `/srv/memex/data`, `/usr/local/bin/claude`) and env-file plumbing live in `infra/docker-compose.yml`, which Phase 5 authors. The Dockerfile here documents the expected mount points via `ENV` defaults so Compose only needs to override secrets.
- Voice/audio captures are forwarded to `/captures/voice`; the worker (Phase 3) does the actual transcription via whisper.cpp. The bot does not transcribe.

### Open questions / known issues
- The retrieval prompt assumes `claude -p` with the vault directory in scope can read files via its built-in tools. If the installed CLI version cannot, the prompt template will need to embed file content in the prompt — that change lives entirely in `prompts/retrieve.md` and is reviewable on its own.
- Telegram's effective inbound file ceiling for bots is ~20 MB, not 25 MB; we keep the 25 MB env cap to match the capture API's ceiling but the practical limit is set by Telegram. The bot rejects files declaring sizes over the cap before downloading; the post-download check handles the rare case where Telegram lies.
- The bot uses `parse_mode="Markdown"` on retrieval messages. CLAUDE.md says "rendered as Markdown"; PTB v20 still accepts the legacy `Markdown` mode but Telegram has been pushing `MarkdownV2`. If Telegram start to reject `Markdown` payloads, switch to `MarkdownV2` and add the v2-required escapes in `rendering.py`.
- `/queue` and `/last` show `(pending)` for rows whose `vault_path` is NULL; this includes both `queued` and `processing` and `failed`. Only the operator's eyes distinguish them today; if the dashboard renders status icons, the bot can adopt the same.
- The bot does not validate at startup that `MEMEX_CAPTURE_API_TOKEN` is accepted by the capture API. A startup probe (`GET /healthz` first, then a no-op `GET /captures?limit=0`) was discussed but deferred — the first user message will surface the misconfiguration with a clear error in logs anyway.

### Test status
- `python -m pytest -q` → **110 passed, coverage 87.57 %** (gate is 85 %).
- Coverage by module: `intent.py` 94 %, `rendering.py` 95 %, `claude_runner.py` 84 %, `capture_client.py` 85 %, `handlers/*` 91–100 %, `queue_reader.py` 96 %, `telemetry.py` 100 %, `auth.py` 100 %, `logging.py` 100 %.
- `bot/main.py` is at 49 % — the uncovered branches are the `build_application`/`main` bootstrap that wire `python-telegram-bot`'s `Application` and the long-poll start; both need a live PTB stack and credentials, and were verified manually instead. The prompt's §3.2 list (whitelist, every intent rule, each capture endpoint, retrieval happy/long/timeout/malformed, every command, logging, auth headers) is fully exercised.
- No skipped or flaky tests.
- The capture API's bearer-token header is asserted on every mocked request.
- The chunker test for the code-fence rule constructs a fenced block of ~2200 lines and verifies every produced chunk has an even fence count.

### Notes for the next phase
- **Compose (Phase 5):** mount the host's `claude` binary at `/usr/local/bin/claude` (read-only). Mount `/srv/memex/data` (the SQLite WAL set) read-write because the bot writes to `claude_calls`. Mount the vault read-only (the bot only ever reads it via `claude -p`, never writes). The bot needs network egress to `api.telegram.org` only — no inbound ports; do not publish anything from this service.
- **Compose env file:** `MEMEX_CAPTURE_API_TOKEN` for the bot must equal the value of `MEMEX_CAPTURE_TOKEN_telegram` in the capture API service. The `submitter` column will then read `api:telegram` per the Phase 1 tracker note.
- **Dashboard (Phase 6):** the retrieval prompt template at `telegram_bot/prompts/retrieve.md` is the same shape the dashboard backend should ship. The two surfaces share the JSON envelope schema (CLAUDE.md "Retrieval response schema"); only the renderer differs (3 messages vs 1 chat bubble). `bot/claude_runner.py::invoke` is reusable verbatim; `bot/rendering.py` is bot-specific.
- The bot's container working directory is `/app`; the prompt template at runtime is read from `/app/prompts/retrieve.md`. The temp-file directory is irrelevant — downloads are in-memory.
- The bot writes one row to `claude_calls` per retrieval, even on transient/timeout failures. Rate-limit dashboards should expect non-zero exit codes (`-1` timeout, `-2` malformed JSON, `-3` transient) as part of normal traffic rather than alert-worthy anomalies.
- A `/find` argument that strips to empty replies with `Usage:` and does **not** call `claude -p`; the same is true for `/capture` with no body. The dashboard's chat surface should mirror this guard.
