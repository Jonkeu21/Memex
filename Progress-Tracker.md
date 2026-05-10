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

---

## Phase 5 — Compose orchestration & bootstrap

**Date completed:** 2026-05-10
**Session model:** Claude Opus 4.7 (1M context)

### What was built
- `infra/docker-compose.yml` — four-service stack (`capture_api`, `worker`, `telegram_bot`, `syncthing`) with named `claude_auth` volume, internal `memex_net` bridge, per-service memory limits, healthchecks, and a clearly-marked `# Phase 6: dashboard goes here` insertion point.
- `infra/.env.example` — fully commented template covering every env var the compose file interpolates plus every service-side env var loaded via `env_file`.
- `worker/Dockerfile` — replaced the runtime stage with one that adds Node + the `@anthropic-ai/claude-code` npm package, downloads `ggml-base.en.bin` to `/models/`, and sets `HOME=/home/memex` plus `MEMEX_WORKER_CLAUDE_BIN=/usr/local/bin/claude`.
- `telegram_bot/Dockerfile` — same Claude-CLI install, plus `procps` for the pgrep healthcheck. Removed Phase 4's "claude binary mounted from host" model since Phase 5 bundles it.
- `capture_api/Dockerfile` — left intact; defaults are overridden by compose to point at the canonical `/srv/memex/data/memex.db` path.
- `scripts/bootstrap.sh` — interactive, idempotent first-time setup driver (root refusal, arch check, docker probe, prompts, `openssl rand -hex 32` capture token, host-dir creation via `sudo mkdir`, `infra/.env` writer with `--force` backup, `docker compose build`, headless `claude /login`, `up -d`, health-poll, self-test capture, operator summary).
- `scripts/teardown.sh` — `down`, optional `--prune-images`, `--reset-claude-login` (volume rm with confirm), `--wipe-data` (deletes vault + queue, two confirms).
- `scripts/lib/prompt.sh` — input + validation helpers (`ask`, `ask_yn`, validators for tokens, chat IDs, abs paths, ints, whisper models).
- `scripts/lib/claude_login.sh` — drives `docker compose run --rm worker claude /login` with a clear pre-flight explanation, then a no-op `claude -p ping` smoke test inside the same volume context.
- `docs/deployment.md` — full operator-facing guide: hardware, OS prep (incl. `/boot/firmware/cmdline.txt` cgroup tweak), Tailscale, bootstrap walkthrough, headless-login UX, first capture test, ops runbook, recovery scenarios, gotchas.
- `tests/compose/test_compose_config.py` — 31 pytest assertions over the parsed `docker compose config` output: services present, ARM64 platform, restart policy, json-file logging with rotation, memory limits and total budget, healthcheck shapes, depends_on health gates, vault/data RO on telegram_bot and RW on worker/capture_api, `claude_auth` volume scoped to exactly worker + telegram_bot, capture_api publishes no host ports, syncthing UI bound to 127.0.0.1.
- `tests/compose/test_env_coverage.py` — three assertions: every `${VAR}` in compose has an `.env.example` entry, every documented entry is referenced (or explicitly intentional), and `MEMEX_CAPTURE_API_TOKEN` is wired from `MEMEX_CAPTURE_TOKEN_telegram`.
- `tests/compose/test_bootstrap.bats` — 6 bats cases: shellcheck clean, dry-run rejects bad tokens, dry-run accepts a valid configuration, dry-run rejects relative paths, refuses to run as root, rejects unknown flags. Tests skip gracefully when the test runner itself is root.

### Key decisions made (and why)
- **Compose file at `infra/docker-compose.yml`** (not the repo root). CLAUDE.md's "Repository layout" section pins it there; Phase 2/3/4 set the precedent of CLAUDE.md winning over the prompt when they disagree. `bootstrap.sh` and `teardown.sh` always pass `-f infra/docker-compose.yml`, so operators never have to remember the path.
- **Project name `memex`** (not the prompt's `secondbrain`). Matches the package names, the `/srv/memex/...` host paths CLAUDE.md uses, and every existing env-var prefix.
- **Host paths `/srv/memex/{vault,data,syncthing}`** — same reason. `MEMEX_VAULT_PATH`, `MEMEX_DATA_PATH`, `MEMEX_SYNCTHING_CONFIG` are operator-overridable in `.env`.
- **Claude CLI installed via `npm install -g @anthropic-ai/claude-code`** rather than the new `curl https://claude.ai/install.sh | bash` native installer. The native installer puts files inside `~/.claude/local/`, which would conflict at runtime with our `claude_auth` volume mount at `/home/memex/.claude` (the volume would shadow the binary). The npm path puts the binary at `/usr/local/bin/claude` — completely outside `~/.claude/` — so the volume only ever holds auth state. Anthropic flags the npm package as deprecated upstream but it still works and is the only install method that's compatible with mounting a credentials volume at `~/.claude`. Phase 6 should keep this approach for the dashboard until/unless Anthropic changes the native installer's layout.
- **Headless `claude /login` flow:** the bootstrap script `docker compose run --rm --no-deps --entrypoint /usr/local/bin/claude worker /login`, attaches the operator's TTY, and the CLI's own URL+code device-flow does the rest. The operator opens the URL on their laptop, signs in to Anthropic, copies the code Anthropic shows them, and pastes it back into the SSH session. After the CLI exits we run a `claude -p --output-format json "ping"` in the same volume context as a smoke test. This is the upstream-supported headless flow as of May 2026; we did not have to implement a Mac-side login + state-copy fallback.
- **Single `claude_auth` named volume** mounted by both `worker` and `telegram_bot` (and, in Phase 6, the dashboard). One `claude /login` covers the entire stack.
- **Memory budget** sized for a 4 GB Pi 5: capture_api 256 MiB, worker 1024 MiB (whisper.cpp + claude subprocess + extraction toolchain), telegram_bot 384 MiB (long-poll + claude subprocess), syncthing 256 MiB. Total 1920 MiB, leaving ~2 GiB for the host kernel, Pi-hole, and Linux page cache for the vault. The math is in the comment block at the top of `infra/docker-compose.yml`.
- **Syncthing image pinned to `syncthing/syncthing:1.27.10`.** v1.27.10 is multi-arch with a published `linux/arm64` manifest, runs cleanly on Pi 5, and is the most recent v1 stable. We pinned to a tag (not a digest) so security updates inside the 1.27.x line are picked up by `docker compose pull` without an edit; bumping a major is a deliberate compose-file change.
- **Telegram-bot healthcheck is a `pgrep` process-presence probe**, not a heartbeat-file probe. Phase 4's bot does not write a heartbeat file, and the prompt forbids modifying service code outside the Dockerfile. The Dockerfile installs `procps` so `pgrep -f "python -m bot.main"` works inside the container. Compose's restart policy is the recovery mechanism if the process disappears.
- **Worker healthcheck is the heartbeat-file probe** the worker already maintains (`MEMEX_WORKER_HEALTHCHECK_PATH=/tmp/memex-worker.healthy`, touched at the end of every poll tick). The compose file declares it explicitly so `docker compose config` exposes it for tests; the Dockerfile keeps the same HEALTHCHECK as a fallback for non-compose runs.
- **`env_file: ./.env` plus per-service `environment:` blocks.** `env_file` pushes everything in `infra/.env` (including the dynamic `MEMEX_CAPTURE_TOKEN_<LABEL>` set the capture API needs) into each container; the `environment:` blocks override defaults and pin the canonical paths (`/srv/memex/data/memex.db`, `/vault`, etc.). Tests assert that the bot's `MEMEX_CAPTURE_API_TOKEN` is wired specifically from `MEMEX_CAPTURE_TOKEN_telegram` so `submitter='api:telegram'` keeps working per Phase 1's note.
- **No reverse proxy, no public ports.** `capture_api` does not publish any host port — the bot reaches it by service name on `memex_net`. Only Syncthing publishes (sync ports + LAN discovery), and its UI is bound to `127.0.0.1:8384` so operators reach it via SSH tunnel or Tailscale serve.

### Deviations from the prompt spec
- **Compose file at `infra/docker-compose.yml`, not the repo root.** Per CLAUDE.md (binding when it and the prompt disagree). Bootstrap and teardown scripts always pass `-f` so the operator never types the path.
- **Project / host paths use `memex`, not `secondbrain`.** Same reason: CLAUDE.md is binding and every existing identifier is `memex`-prefixed.
- **Telegram-bot healthcheck is process-presence, not last-poll-timestamp.** Phase 4's bot doesn't maintain a heartbeat file and the prompt forbids modifying its code; documented above.
- **Capture-API token env-var is `MEMEX_CAPTURE_TOKEN_<LABEL>`** (Phase 2's choice from CLAUDE.md), not the prompt's bare `CAPTURE_API_TOKEN`. Bootstrap auto-fills `MEMEX_CAPTURE_TOKEN_telegram` from `openssl rand -hex 32` so the operator never sees the underlying name.
- **`shared/memex_shared/` extraction is still deferred.** Phase 4 already noted this; nothing in Phase 5 forced the issue. Phase 6 (dashboard) will be the fourth service carrying a near-identical `logging.py` if it's not extracted by then.

### Deferred / left for later phases
- **Dashboard service (Phase 6).** A `# Phase 6: dashboard goes here` block in `infra/docker-compose.yml` documents the expected shape: build context `../dashboard`, depends_on `capture_api` healthy, `${MEMEX_VAULT_PATH}:/vault:ro`, `${MEMEX_DATA_PATH}:/srv/memex/data:ro`, `claude_auth:/home/memex/.claude`, no published ports (Tailscale serves it), `mem_limit ~256m`. Adding a `dashboard` service should not require any change to bootstrap or teardown — the script discovers services through `docker compose ps`/`config`.
- **`shared/memex_shared/` package.** Same as Phase 4's note. Once the dashboard lands, four near-identical loggers + two queue DDL copies will exist; that is the right moment to extract.
- **Tailscale ACL templates** for the operator. Not authored here; the deployment guide just points at the upstream installer and notes that the Syncthing UDP ports must be allowed if the ACLs are tightened.
- **`tailscale serve` config** for exposing the Syncthing UI / dashboard — left for the operator to author once Phase 6 ships and there's something to expose.
- **Container image signing / SBOM.** No cosign signatures, no SBOM emission, no image scanning. Single-user homelab.
- **Periodic vault backups.** The deployment guide lists the rsync command but does not install a cron / systemd timer.

### Open questions / known issues
- **The npm `@anthropic-ai/claude-code` package is upstream-deprecated.** It works today, and is the only install path that doesn't conflict with a `~/.claude` volume mount, but Anthropic could remove it. If/when that happens we'll need to either (a) carve a separate `~/.claude-bin` install location and adjust the install script's prefix, or (b) install the native binary in a build stage and copy it into the runtime image, leaving auto-update disabled.
- **Syncthing tag `1.27.10` is pinned by tag, not by digest.** A pinned digest would be more reproducible but requires a manual digest lookup; we pin to the tag and document the bump path. The deployment guide flags this.
- **The Pi user's uid/gid (1000/1000) is captured at bootstrap time and burned into `infra/.env` as `MEMEX_UID`/`MEMEX_GID`.** If the operator later changes their uid (e.g. by recreating the user), Syncthing will lose write access until they edit `infra/.env` and `up -d` the syncthing service.
- **Compose interpolation does not see vars exported by `env_file`.** The pattern `${MEMEX_CAPTURE_TOKEN_telegram}` works only because `infra/.env` is also the `--env-file` source for compose; if an operator separates them they will see an empty bot token. Bootstrap doesn't separate them.
- **`docker compose run --rm --entrypoint /usr/local/bin/claude worker /login` uses `--no-deps`** so the capture API isn't started just to do a login. If the worker image's runtime user can't write `/home/memex/.claude/credentials.json` for any reason (e.g. SELinux, AppArmor), the login will silently appear to succeed but the volume will be empty; the smoke test catches this.
- **Bats tests skip when run as root** because `bootstrap.sh` refuses to run as root. CI runners that run as root see the suite report 4 skipped + 2 passed; they should `runuser -u <non-root>` if they want full coverage.

### Test status
- `python -m pytest tests/compose/` → **34 passed** (compose config 31, env coverage 3). Includes parametrised checks across all four services for platform, restart, logging, and memory.
- `bats tests/compose/test_bootstrap.bats` → **6 ok** when run as a non-root user (`su <user> -c 'bats ...'`); 4 skip + 2 pass when run as root, with a clear skip reason.
- `shellcheck --severity=warning -x scripts/*.sh scripts/lib/*.sh` → clean.
- `docker compose -f infra/docker-compose.yml --env-file <env> config` exits 0 against the synthetic env in the test fixture.
- Not tested: an actual Pi 5 build of the worker / telegram_bot images. The `npm install -g @anthropic-ai/claude-code` step requires network egress and fetches an arm64-compatible binary; this should be exercised on the Pi during the first real bootstrap. Same for `whisper.cpp v1.7.2`'s arm64 build.
- Not tested: an end-to-end "send URL to bot, see file in vault" round-trip. Acceptance criterion 2 in the prompt requires a Pi to exercise.

### Notes for the next phase
- **Dashboard insertion point** is in `infra/docker-compose.yml`; the `# Phase 6: dashboard goes here` block lists the expected mounts, depends_on, and memory budget. Add the service definition there; do NOT introduce a separate compose override file.
- **Claude auth volume name** is `memex_claude_auth` (the docker-level name; the compose-level alias is `claude_auth`). Mount it on the dashboard container at `/home/memex/.claude` so retrieval calls reuse the same login.
- **Port conventions:** capture_api binds 8001 inside the network and is unpublished. The dashboard should pick a different free port (suggested 8002) and either stay unpublished (Tailscale-served) or publish to `127.0.0.1` only.
- **Memory headroom:** the budget leaves ~2 GiB free. The dashboard backend (FastAPI + a few SQLite reads + occasional `claude -p`) should fit in 256 MiB; the React build is static and served from inside that same container.
- **`env_file: ./.env`** is the pattern; the dashboard service must also point at it so it picks up `MEMEX_LOG_LEVEL` and any future cross-cutting vars.
- **Bootstrap script** does not need to know about the dashboard explicitly. Adding a service to compose is enough; `docker compose up -d` from the existing flow brings it up.
- **Teardown's `--prune-images`** lists images by name; add `memex/dashboard:latest` to the loop in `scripts/teardown.sh` when the dashboard ships.
- **The capture API's `env_file`** loads every `MEMEX_CAPTURE_TOKEN_*` label automatically; the dashboard, if it makes capture calls, should be configured with `MEMEX_CAPTURE_API_TOKEN=${MEMEX_CAPTURE_TOKEN_dashboard}` and `MEMEX_CAPTURE_TOKEN_dashboard` set in `.env` — `submitter` will then read `api:dashboard`.
- **Worker / telegram_bot / capture_api Dockerfiles all run as uid 10001** (`memex` user). The dashboard should follow suit so the bind-mounted vault has uniform ownership semantics across services.

---

## Phase 6 — Web dashboard

**Date completed:** 2026-05-10
**Session model:** Claude Opus 4.7 (1M context)

### What was built

Backend (FastAPI):
- `dashboard/pyproject.toml` — backend deps + pytest config; package name `backend`, tests run from `dashboard/` root.
- `dashboard/backend/__init__.py` — package marker.
- `dashboard/backend/app.py` — FastAPI factory, lifespan, JSON access-log middleware, six routers under `/api/v1/...`, and SPA mount at `/` that serves `frontend/dist/` when present.
- `dashboard/backend/auth.py` — bearer-token dependency using `secrets.compare_digest` (constant-time, length-padded).
- `dashboard/backend/config.py` — env-driven `Settings` dataclass with `MEMEX_DASHBOARD_*` prefix.
- `dashboard/backend/db.py` — SQLite connect helper (read+write, WAL, busy_timeout) and a `table_exists` check used by the rate-limit endpoint.
- `dashboard/backend/logging.py` — structured-JSON logger, `service="dashboard"`, same redaction rules as capture_api/worker/telegram_bot.
- `dashboard/backend/schemas.py` — pydantic v2 models for every request/response across all six routers.
- `dashboard/backend/vault.py` — path-safety boundary; `safe_join`, `safe_join_existing`, `vault_relative`, `ensure_subdir`, `is_inbox_path`. NUL-byte / `..` / drive-letter rejection, `Path.resolve(strict=True).relative_to(root)` enforcement, symlink-escape rejection.
- `dashboard/backend/frontmatter.py` — minimal YAML front-matter parser + targeted field patcher (for clearing `needs_review`/updating `taxonomy_path` on inbox routing).
- `dashboard/backend/taxonomy_io.py` — load/parse/validate/render `taxonomy.yml`. Validation rules mirror `worker/worker/taxonomy.py` so the worker doesn't reject what the dashboard writes; depth-limit added (max 6).
- `dashboard/backend/claude_runner.py` — subprocess wrapper for `claude -p`. Mirrors `telegram_bot/bot/claude_runner.py` (envelope shapes, inner JSON validation, quote truncation). Adds a dedicated `ClaudeNotAuthenticatedError` that maps to a clean 503 in the retrieval router instead of a generic 502.
- `dashboard/backend/routers/health.py` — `/healthz` (open) and `/readyz` (probes SQLite + vault dir).
- `dashboard/backend/routers/queue.py` — `GET /api/v1/queue`, `GET /api/v1/queue/{id}`, `POST .../retry`, `POST .../cancel`. Retry only allowed from `failed` or `needs_review`; cancel only from `queued` or `needs_review`; both 409 otherwise.
- `dashboard/backend/routers/inbox.py` — `GET /api/v1/inbox`, `GET .../{path}`, `POST .../{path}/route`, `POST .../{path}/delete`. Routing patches front-matter (`needs_review: false`, `taxonomy_path: <target>`) atomically before the rename. Delete moves to `_trash/<YYYY-MM>/<filename>` — never `unlink`.
- `dashboard/backend/routers/taxonomy.py` — `GET` returns the parsed doc + raw YAML; `PUT` validates → renders → atomic-writes. Failed PUTs do not corrupt the on-disk file.
- `dashboard/backend/routers/captures.py` — walks PARA folders + `_inbox/` for `*.md`, parses front-matter, sorts newest-first, paginates server-side. Search is over titles/path/tags. Body endpoint serves the parsed markdown.
- `dashboard/backend/routers/rate_limit.py` — reads `claude_calls`. Returns 24-hour total, per-hour x per-service stacked-bar buckets, 5-minute rolling error rate, last 20 calls, services breakdown. Returns `available: false` (with empty arrays, 200) if the table doesn't exist yet.
- `dashboard/backend/routers/retrieval.py` — `POST /api/v1/retrieval`. Reads `prompts/retrieve.md`, calls `claude -p` via `asyncio.to_thread`, validates the envelope, marks `sources[i].exists` based on disk presence, appends a row to `claude_calls` with `service='dashboard'`. Maps timeout→504, not-authenticated→503, malformed-JSON/transient→502.
- `dashboard/backend/prompts/retrieve.md` — versioned prompt template (`prompt_version: 1`). Near-duplicate of `telegram_bot/prompts/retrieve.md` with a header comment about why the duplication exists.

Frontend (React + Vite + MUI v5 + Minimal-UI-Kit theme):
- `dashboard/frontend/package.json`, `tsconfig.json`, `tsconfig.node.json`, `vite.config.ts`, `vitest.config.ts`, `index.html`.
- `dashboard/frontend/src/theme/{palette,typography,shadows,overrides,index}.ts` — primary green `#00A76F`, Public Sans, custom multi-layer shadows, card radius 16, button radius 8, MUI overrides for `MuiCard`, `MuiButton`, `MuiTextField`, `MuiTableCell`, `MuiAppBar`, `MuiTooltip`, `MuiChip`, `MuiPaper`, `MuiDrawer`. Light + dark palettes with the same accent.
- `dashboard/frontend/src/types/api.ts` — TypeScript mirror of `backend/schemas.py`; kept in sync by hand.
- `dashboard/frontend/src/api/{client,endpoints}.ts` — fetch wrapper with token attachment (opt-in `withAuth`), typed endpoint module covering every router.
- `dashboard/frontend/src/hooks/{useToken,useThemeMode}.ts` — localStorage-backed token + theme/density persistence. `useToken` fan-outs to subscribers so settings drawer changes propagate without a route reload.
- `dashboard/frontend/src/components/Layout/{AppShell,Sidebar,TopBar}.tsx` — top app bar with search + theme toggle + settings cog; sidebar with grouped nav and the Minimal-style green pill + dot active indicator.
- `dashboard/frontend/src/components/{SettingsDrawer,StatusChip,MarkdownViewer}.tsx` — settings drawer (token, theme, density), status chip with kit-style coloured background, lazy-loaded `react-markdown` viewer.
- `dashboard/frontend/src/pages/{Queue,Inbox,Taxonomy,Captures,RateLimit,Retrieval}.tsx` — six pages.
- `dashboard/frontend/src/{App,main}.tsx` — Router + ThemeProvider + QueryClientProvider; loads Public Sans via `@fontsource/public-sans`.

Tests + ops:
- `dashboard/tests/backend/conftest.py` — vault + queue + claude_calls fixtures; `client`, `auth_headers`, `insert_queue_row`, `insert_claude_call`.
- `dashboard/tests/backend/test_{vault_safety,auth,queue,inbox,taxonomy,captures,rate_limit,retrieval,misc}.py` — 184 tests, **88.88 % coverage** on `backend/`.
- `dashboard/tests/frontend/setup.ts` — vitest setup, mocks `MarkdownViewer` and `react-apexcharts` so jsdom is happy.
- `dashboard/tests/frontend/{pages.test.tsx,retrieval.test.tsx}` — 12 Vitest smoke tests across all six pages including a happy-path retrieval flow.
- `dashboard/tests/frontend/retrieval.e2e.spec.ts` — Playwright placeholder; full e2e suite deferred (see §"Deferred").
- `dashboard/Dockerfile` — multi-stage: Node 20 builds `frontend/dist/`, Python 3.11-slim runtime serves the bundle alongside the FastAPI backend. uid/gid 10001 (`memex`), ARM64-compatible.
- `dashboard/README.md` — operator-facing dev + deploy + troubleshooting guide.
- `infra/docker-compose.yml` — replaced the Phase 5 placeholder with a real `dashboard` service: builds from `../dashboard`, depends_on `capture_api` healthy, mounts `claude_auth`, mounts vault + data **read-write** (triage moves files; retry updates queue rows), publishes `0.0.0.0:8002`, mem_limit `384m`, healthcheck on `/healthz`. Memory-budget comment block updated; total budget now 2304 MiB (~1.7 GiB free for kernel + Pi-hole + page cache).
- `infra/.env.example` — added `MEMEX_DASHBOARD_BEARER_TOKEN` (with `openssl rand -hex 32` instructions) and `MEMEX_DASHBOARD_CLAUDE_TIMEOUT_SECONDS`.
- `scripts/bootstrap.sh` — generates `DASHBOARD_TOKEN` alongside `CAPTURE_TOKEN`, writes the new env-vars, and prints the dashboard URL + token in the closing summary.
- `scripts/teardown.sh` — `--prune-images` now also removes `memex/dashboard:latest`.
- `tests/compose/test_compose_config.py` — added 9 dashboard-specific assertions (presence in services, ARM64, restart, logging, memory limit, http healthcheck, depends_on capture_api, publishes 8002, vault rw, data rw, claude_auth volume mount). Total compose tests now 43 (was 34).
- `.gitignore` — added entries for `dashboard/frontend/node_modules/`, `dashboard/frontend/dist/`, and the `dashboard/node_modules` symlink used during local test runs.

### Key decisions made (and why)
- **Vault and data are mounted read-WRITE on the dashboard.** The Phase 5 placeholder said `:ro`, but inbox routing has to move files and queue retry/cancel has to update rows. `:ro` would have produced cryptic permission errors at runtime; `:rw` is the right shape for an operator workstation surface, and the bearer-token dependency is what actually gates mutation.
- **Single shared bearer token, no labels.** The capture API uses a `MEMEX_CAPTURE_TOKEN_<LABEL>` map because it has multiple submitters needing audit (`api:telegram`, etc.). The dashboard has one operator. A label scheme would be surface area without value, so `MEMEX_DASHBOARD_BEARER_TOKEN` is one secret, compared with `secrets.compare_digest`.
- **Read-only routes are open on the tailnet.** Tailscale is the trust boundary; gating list/get/search behind a token would trip up the operator's mobile session every time they look up a note. Mutating routes are gated.
- **Tests outside `frontend/`** (per the prompt's `dashboard/tests/{backend,frontend}/` layout) require a `dashboard/node_modules` symlink to `frontend/node_modules` for vitest's module resolution. The symlink is git-ignored and documented in the README. Workspaces would have been cleaner but would have changed the dependency root in a way that breaks the prompt's expected file structure.
- **`backend.claude_runner` is a near-duplicate of `telegram_bot/bot/claude_runner.py`** rather than an import. The `shared/memex_shared/` extraction is still deferred (Phase 4/5 noted this); duplicating one more module is the lesser evil vs. taking a runtime dependency on the bot package. New: `ClaudeNotAuthenticatedError` is a dashboard-only addition that pattern-matches on common stderr markers from the CLI to give the retrieval chat a clean 503 instead of a generic 502 when the volume is empty. (Acceptance criterion 17.)
- **Trash, not unlink.** Inbox "delete" moves to `_trash/<YYYY-MM>/<filename>`. The vault is irreplaceable; the dashboard's UI tooltip says so prominently. CLAUDE.md doesn't currently document `_trash/`; this entry is the canonical record. If a future contract revision wants to hoist this, bumping `contract_version` is the right move.
- **The retrieval renderer is a single chat bubble**, per CLAUDE.md "Retrieval response schema". The Telegram bot does three messages; the dashboard does one card with answer / source chips / excerpts. Both consume the same JSON envelope; the only divergence is layout.
- **Server-side captures search.** I considered shipping a SQLite FTS index to make this fast on a big vault, but for a single-user homelab a synchronous `Path.rglob('*.md')` is fine up to ~10 k files. The endpoint returns `next_cursor` so a future paginated UI can lazy-load. If/when this becomes a bottleneck the right place to add an index is `worker/` (so it's maintained as captures are filed) rather than the dashboard.
- **ApexCharts via `react-apexcharts`** for the rate-limit gauge + stacked bars. The Minimal UI Kit's reference screenshots use ApexCharts; recharts would have been smaller but wouldn't match the half-donut gradient cleanly. Charts are lazy-loaded via dynamic import so they don't affect first paint.
- **No state-management library.** React Query for server cache, component state for the rest. Six pages don't justify Redux/Zustand.
- **Multi-stage Dockerfile installs the package via pip from a copied pyproject.toml**, then re-copies the source to `/app/` for runtime. This lets the wheel build use just the deps + source, while the final image references `backend/` via the canonical project layout.

### Deviations from the prompt spec
- **Dashboard mounts vault and data read-WRITE**, not read-only as Phase 5's placeholder suggested. The prompt itself says "the dashboard mounts the vault read-write so triage actions can move files; mutations are gated by the shared bearer token", so this matches the prompt; the deviation is from the Phase 5 placeholder, which was unaware of triage requirements.
- **The dashboard publishes 8002 on `0.0.0.0`**, not unpublished as the Phase 5 handoff suggested. The prompt requires the dashboard to be reachable at `http://<pi-tailscale-name>:<port>` over the tailnet, which means a host port binding. The Pi has no public ingress (no port 80/443 forwarding) so this is tailnet-only by construction; documented in the compose file's port comment.
- **Frontend tests live at `dashboard/tests/frontend/`** per the prompt's expected layout, not inside `dashboard/frontend/tests/`. This requires a git-ignored symlink at `dashboard/node_modules` for vitest's module resolution. Documented in README.
- **No real Playwright e2e test**; the file is a placeholder explaining why. The Vitest happy-path covers the same input → loading skeleton → answer flow against a mocked API. Wiring up Playwright + a real backend would have at least doubled the test surface for the same risk coverage. See "Deferred".

### Deferred / left for later phases
- **Playwright e2e suite.** A real-backend, real-build e2e of the retrieval chat (and ideally a smoke run on the Pi after `docker compose up`). The Vitest suite covers the same path against a mocked API, but the file at `tests/frontend/retrieval.e2e.spec.ts` is currently a placeholder. Future maintenance should set up `playwright install --with-deps`, a Vite preview server, and a single happy-path script.
- **`shared/memex_shared/` extraction** is still deferred — now four services carry a near-identical `logging.py` and three carry the `claude -p` runner. The right time to extract would be the moment a fifth caller appears or any of the four diverges; for now duplicating is cheaper than a refactor across all four.
- **No FTS-style search on the captures browser.** Synchronous `rglob('*.md')` works for the operator's vault size today; a SQLite FTS5 index maintained by the worker is the natural upgrade path.
- **Lighthouse / accessibility audit** has not been run as part of this phase. The acceptance criterion is "≥ 90 on the chat page (smoke check)". Manual review covered ARIA labels, keyboard navigation, colour-only state indicators, and tooltips on disabled buttons; a real Lighthouse run on a Pi-served instance is the verification step.
- **Dark mode contrast pass.** The dark palette is functional but hasn't been side-by-side compared with the Minimal UI Kit's dark-mode screenshots (none provided).
- **Mobile layout pass.** Pages render and are usable on a phone but the inbox + captures tables are dense; a future iteration should switch to card layouts under `xs`.
- **`obsidian://open?path=` query parameter naming.** The plugin docs vary between `path` and `file`; we ship `path` (which the operator's Mac Obsidian honours). If your client treats it differently, the markdown viewer panel is the always-available fallback.
- **CLAUDE.md does not yet document `_trash/`.** This entry is the canonical record of the convention. A patch bump (1.0.1) would be appropriate to add the line about `_trash/` to the "Vault folder structure" section in a future PR.

### Open questions / known issues
- **Frontend bundle size:** main chunk is ~165 kB gzipped, charts chunk ~158 kB gzipped, markdown chunk ~50 kB gzipped. All under the < 1 MB target. Most weight is MUI v5; if this becomes a problem on the Pi-served path, MUI's `@mui/base` + tree-shaken icons would reclaim ~50 kB.
- **Dashboard memory cap is 384 MiB** (matching `telegram_bot`). The actual resident set should be tiny since the React build is static and FastAPI's working set is small; the cap is set conservatively to absorb a `claude -p` retrieval subprocess.
- **`@anthropic-ai/claude-code` npm package is upstream-deprecated** (Phase 5 noted this). The dashboard inherits the worker's install path via the shared `claude_auth` volume — if Anthropic removes the npm package the worker's image build is what breaks, not the dashboard's.
- **The frontend's `tests/frontend/` location requires a symlink** for module resolution (see "Key decisions"). CI without the symlink will fail to find `@testing-library/dom`. The README documents the one-liner.
- **`obsidian://` fires unconditionally**; the dashboard does not detect whether Obsidian is actually installed on the client. The fallback is the in-app markdown viewer, which is always available.
- **The retrieval prompt is duplicated** between `dashboard/backend/prompts/retrieve.md` and `telegram_bot/prompts/retrieve.md`. A header comment documents the duplication; updates must land in both files in the same PR to keep the contract honest.

### Test status
- `python -m pytest tests/backend/` (run from `dashboard/`) → **184 passed, 88.88 % coverage** on `backend/` (gate is 85 %). Slowest tests are the inbox routing fixtures (front-matter parsing on temp files); none is flaky.
- `npm test` (run from `dashboard/frontend/`) → **12 passed** across `pages.test.tsx` (10) and `retrieval.test.tsx` (2). Covers each page rendering + a happy-path retrieval flow with input → loading skeleton → rendered answer + sources + excerpts.
- `npm run build` succeeds; bundle sizes documented above.
- `npm run lint` (`tsc --noEmit`) → clean on `src/`.
- `python -m pytest tests/compose/` (run from repo root) → **43 passed** (was 34 in Phase 5; added 9 dashboard-specific checks: presence, ARM64, restart, logging, memory limit, http healthcheck, depends_on, publishes 8002, vault/data rw mounts, claude_auth volume mounted).
- Not tested: an actual Pi 5 build of the dashboard image. The multi-stage Dockerfile uses standard `node:20-bookworm-slim` and `python:3.11-slim` bases that have published `linux/arm64` manifests; this should work but should be exercised on a real Pi during the next deploy.
- Not tested: the full e2e flow (capture from Telegram → worker files note → dashboard inbox empty → retrieval chat finds it). Acceptance criterion in the prompt; needs a Pi to verify.
- Not tested: Lighthouse accessibility score. Manual review covered ARIA labels and keyboard navigation.

### Notes for future iterations
- **Extract `shared/memex_shared/`.** Four copies of the structured logger, three copies of the `claude -p` runner, two copies of the queue DDL. The right shape is a small Python package with `logging.py`, `claude.py`, `taxonomy.py`, `frontmatter.py`, and the queue + claude_calls DDL. Each service installs it as a path dep.
- **Server-side captures search via FTS5.** The worker writes a row to a `captures_fts` virtual table when it files a note; the dashboard queries it. Cleaner than synchronous `rglob` and more useful as the vault grows.
- **Real Playwright e2e** against a Vite preview + a real backend, plus a Lighthouse run. Both are a half-day of work; deferring to keep this phase focused.
- **Drag-and-drop reorder** on the taxonomy editor would feel better than the current up/down arrows. `@dnd-kit/core` is a clean fit.
- **The captures viewer panel** currently renders markdown only. A small "view raw front-matter" toggle would help when debugging worker filing decisions.
- **The retrieval chat's "low confidence" warning** triggers below 0.5. After a week of real use the threshold may want to be different — make it configurable from the settings drawer.
- **Front-matter patcher** in `frontmatter.py` is a hand-rolled regex-aware string replace because we deliberately avoided round-tripping through PyYAML (which would lose comments and ordering). If a future contract revision adds nested front-matter fields, the patcher will need to be smarter; consider switching to `ruamel.yaml` round-trip mode at that point.
- **Bundle-size budget** is fine today but MUI v5 is the dominant cost. A future iteration could switch to `@mui/base` + a hand-rolled component layer matching the Minimal kit; would reclaim ~50–100 kB gzipped from the main chunk.
- **The dashboard's healthcheck is `/healthz`** (open). `/readyz` additionally verifies the SQLite handle and vault mount. Compose only checks `/healthz`; consider running `/readyz` once at start-period via a separate probe to fail fast on misconfig. (We didn't because the existing services use the simple `/healthz` pattern; consistency wins for now.)


