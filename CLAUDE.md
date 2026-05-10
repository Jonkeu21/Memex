---
contract_version: 1.0.0
---

# CLAUDE.md — Memex architecture & contracts

## Purpose & scope

This file is the binding contract for every component in the Memex stack: the capture API, the processing worker, the Telegram bot, the web dashboard, and the Compose orchestration. Every Claude Code session loads it on start and treats the schemas, names, and routing rules below as normative. Prose explains why a rule exists; the rule itself is whatever appears inside a fenced block, a table, or a numbered list. When this file and a downstream implementation disagree, the implementation is wrong.

## System overview

| Component | Responsibility (one line) |
| --- | --- |
| `capture_api` | FastAPI service that validates inbound captures, persists them to the SQLite queue, and returns immediately. |
| `worker` | Long-running Python process that pulls queued items, extracts content, shells out to `claude -p` for filing, writes notes into the vault, and updates the queue row. |
| `telegram_bot` | Single bot for both capture (forwards to capture API) and retrieval (shells out to `claude -p` with the vault as context). |
| `dashboard` | FastAPI + React app (Minimal UI Kit) for queue monitoring, `_inbox/` triage, taxonomy editing, retrieval chat, and rate-limit telemetry. |
| `syncthing` | Bidirectional sync of the vault between the Pi (canonical) and the Mac (editor). Not authored by us; configured via Compose. |

```text
                 ┌──────────────┐
 user ──msg────► │ telegram_bot │
                 └──┬────────┬──┘
       capture intent│        │retrieval intent
                    ▼        ▼
            ┌────────────┐  ┌────────────────────────────┐
            │ capture_api│  │ claude -p (vault as ctx)   │
            └─────┬──────┘  └─────────────┬──────────────┘
                  │ INSERT                │ JSON response
                  ▼                       │
           ┌────────────┐                 │
           │ sqlite     │                 │
           │  queue     │                 │
           └─────┬──────┘                 │
                 │ SELECT … status='queued'
                 ▼
           ┌────────────┐  write note    ┌──────────────┐
           │ worker     │ ─────────────► │ vault (md)   │
           └─────┬──────┘                └──────┬───────┘
                 │ UPDATE queue row              │ syncthing
                 ▼                               ▼
           dashboard reads queue          Mac (Obsidian editor)
```

## Repository layout

```text
.
├── CLAUDE.md                  # this file (contract)
├── Progress-Tracker.md        # cross-session lab notebook (append-only)
├── README.md
├── capture_api/               # Phase 2 — FastAPI service
│   ├── app/
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
├── worker/                    # Phase 3 — queue consumer + claude -p driver
│   ├── app/
│   ├── prompts/               # filing prompt templates
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
├── telegram_bot/              # Phase 4 — capture + retrieval front-end
│   ├── app/
│   ├── prompts/               # retrieval prompt templates
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
├── dashboard/                 # Phase 6 — FastAPI backend + React (Minimal UI Kit) frontend
│   ├── backend/
│   ├── frontend/
│   └── Dockerfile
├── infra/                     # Phase 5 — orchestration
│   ├── docker-compose.yml
│   ├── .env.example
│   ├── tailscale/
│   └── syncthing/
└── shared/                    # Python package shared by api, worker, dashboard
    ├── memex_shared/
    │   ├── queue.py           # SQLite DDL + dataclasses
    │   ├── schemas.py         # pydantic models for the contracts in this file
    │   ├── taxonomy.py        # taxonomy.yml loader + validator
    │   ├── frontmatter.py     # note front-matter writer/reader
    │   └── logging.py         # structured-JSON logger
    └── pyproject.toml
```

The vault itself lives outside the repo at `/srv/memex/vault` on the Pi and is bind-mounted into the worker, the dashboard backend, and the Telegram bot. The repo never commits vault contents.

## Vault folder structure

The vault uses **PARA** (Projects / Areas / Resources / Archive) as the default taxonomy, plus three reserved folders prefixed with `_` so they sort to the top of Obsidian's file list. PARA was chosen because it is small (four buckets), well documented, and degrades gracefully — anything that doesn't fit cleanly lands in `_inbox/`.

```text
vault/
├── _inbox/         # low-confidence captures awaiting human triage
├── _meta/          # taxonomy.yml, prompt overrides, dashboard scratch
├── _attachments/   # binary blobs (audio, pdf, images) referenced from notes
├── projects/       # active, deadline-bound work (PARA "Projects")
├── areas/          # ongoing responsibilities (PARA "Areas")
├── resources/      # reference material by topic (PARA "Resources")
└── archive/        # inactive items kept for retrieval
```

Notes are markdown with YAML front-matter (see "Front-matter conventions"). Filenames follow `YYYY-MM-DD--<slug>.md` where `<slug>` is the worker-derived title, lowercased, kebab-cased, and truncated to 60 characters.

## Taxonomy file format

The taxonomy lives at `vault/_meta/taxonomy.yml`. YAML is chosen over TOML because the file contains nested keyword lists and per-folder overrides that read more naturally in YAML, and because Obsidian users already author YAML in front-matter. The file is owned by the operator and edited via the dashboard; the worker reads it on every filing decision (no caching across calls).

Schema:

```yaml
schema_version: 1                 # int; bump when the loader's schema changes
default_route: _inbox             # vault-relative folder used when no folder matches
confidence:
  autonomous_threshold: 0.80      # >= this → file directly into matched folder
  review_threshold: 0.60          # [review_threshold, autonomous_threshold) → file with needs_review: true
                                  # < review_threshold → route to _inbox
folders:
  - path: projects/memex
    description: "Active build of the Memex stack itself."
    keywords: [memex, raspberry pi, claude code, second brain]
    confidence_override: null     # null = use global thresholds
  - path: areas/health
    description: "Recurring health logs, lab results, fitness notes."
    keywords: [sleep, hrv, bloodwork, workout, vo2]
    confidence_override:
      autonomous_threshold: 0.85  # higher bar — health misfilings are annoying
      review_threshold: 0.65
  - path: resources/ml-papers
    description: "Reference notes on ML papers, models, evals."
    keywords: [paper, arxiv, transformer, eval, benchmark]
    confidence_override: null
  - path: resources/cooking
    description: "Recipes and cooking technique notes."
    keywords: [recipe, sous vide, baking, sourdough]
    confidence_override: null
  - path: archive/2024
    description: "Items archived during 2024."
    keywords: []
    confidence_override: null
```

Validation rules enforced by `shared.memex_shared.taxonomy`:

1. `schema_version` must equal the loader's supported version.
2. Every `path` must be vault-relative, contain no leading slash, no `..`, and no whitespace.
3. `default_route` must exist as a directory under `vault/`.
4. `0.0 <= review_threshold <= autonomous_threshold <= 1.0`.
5. Folder `path` values must be unique.

## Queue item schema

A single SQLite database lives at `/srv/memex/data/memex.db`, shared via bind mount by the capture API (writer), the worker (writer), and the dashboard backend (reader). WAL mode is on. The capture API and worker open separate connections; no connection is shared across threads.

```sql
CREATE TABLE queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT    NOT NULL,                  -- ISO-8601 UTC, set by capture API
    updated_at      TEXT    NOT NULL,                  -- ISO-8601 UTC, set by every writer
    source_type     TEXT    NOT NULL CHECK (source_type IN ('url','file','text','voice')),
    source_payload  TEXT    NOT NULL,                  -- JSON, shape depends on source_type
    submitter       TEXT    NOT NULL,                  -- 'telegram:<chat_id>' or 'api:<token_label>'
    status          TEXT    NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued','processing','filed','needs_review','failed')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,                              -- short message; full traceback goes to logs
    processed_at    TEXT,                              -- ISO-8601 UTC, set when status leaves 'queued'/'processing'
    confidence      REAL,                              -- [0.0, 1.0], set by worker
    vault_path      TEXT,                              -- vault-relative path of the written note
    claude_session_id TEXT,                            -- worker-side correlation id from claude -p
    claude_input_tokens  INTEGER,
    claude_output_tokens INTEGER,
    claude_duration_ms   INTEGER
);

CREATE INDEX queue_status_created_at ON queue (status, created_at);
CREATE INDEX queue_submitter         ON queue (submitter);
```

Field semantics:

| Field | Writer | Mutability | Notes |
| --- | --- | --- | --- |
| `id` | API | immutable | Primary key. |
| `created_at` | API | immutable | UTC, microsecond precision, ISO-8601 with `Z` suffix. |
| `updated_at` | API + worker | mutable | Updated on every row write. |
| `source_type` | API | immutable | Enum above. Determines `source_payload` shape. |
| `source_payload` | API | immutable | JSON, see shapes below. |
| `submitter` | API | immutable | Used for rate-limit accounting and audit. |
| `status` | API + worker | mutable | API only ever writes `queued`. Worker writes the rest. |
| `attempts` | worker | mutable | Incremented on each `claude -p` call regardless of outcome. |
| `last_error` | worker | mutable | Cleared (set to NULL) on success. |
| `processed_at` | worker | mutable | Set when status moves to `filed`, `needs_review`, or `failed`. |
| `confidence` | worker | mutable | NULL until the worker has a score. |
| `vault_path` | worker | mutable | NULL until the note is written. |
| `claude_*` | worker | mutable | Per-call telemetry; see "Rate-limit accounting". |

`source_payload` shapes by `source_type`:

```json
// url
{"url": "https://example.com/article", "user_note": "optional free text"}

// file
{"original_filename": "scan.pdf", "stored_path": "/srv/memex/data/uploads/<uuid>.pdf",
 "mime_type": "application/pdf", "size_bytes": 184223}

// text
{"text": "raw plain-text body, untouched"}

// voice
{"original_filename": "voice.ogg", "stored_path": "/srv/memex/data/uploads/<uuid>.ogg",
 "mime_type": "audio/ogg", "size_bytes": 41203, "duration_seconds": 17.4}
```

## Capture API surface

Base URL: `http://capture-api:8000` inside the Compose network; published over Tailscale at `https://memex-capture.<tailnet>.ts.net`.

Auth: every request must carry `Authorization: Bearer <token>`. Tokens live in `infra/.env` as `MEMEX_CAPTURE_TOKEN_<LABEL>=<value>`; the API loads them at startup and matches by value, recording the matching `LABEL` as the submitter when the request comes from `api:` sources. Telegram-originated calls use a dedicated token whose label is `telegram`.

Common error envelope:

```json
{"error": {"code": "invalid_payload", "message": "url must be http(s)"}}
```

Common status codes: `400 invalid_payload`, `401 unauthorized`, `413 payload_too_large` (>25 MB body), `500 internal_error`. Happy-path codes are documented per endpoint.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/captures/url` | Queue a URL capture. |
| `POST` | `/captures/text` | Queue a plain-text capture. |
| `POST` | `/captures/file` | Queue a file capture (multipart). |
| `POST` | `/captures/voice` | Queue a voice capture (multipart, audio/*). |
| `GET`  | `/captures` | List queue rows, filterable. |
| `GET`  | `/captures/{id}` | Fetch a single queue row. |
| `GET`  | `/healthz` | Liveness; returns `{"status":"ok"}` with `200`. |

`POST /captures/url`

```json
// request
{"url": "https://example.com/article", "user_note": "skim later"}

// 202 Accepted
{"id": 4123, "status": "queued", "created_at": "2026-05-10T14:22:01.123456Z"}
```

`POST /captures/text`

```json
// request
{"text": "raw body here"}                    // text required, 1..100000 chars

// 202 Accepted
{"id": 4124, "status": "queued", "created_at": "..."}
```

`POST /captures/file` — `multipart/form-data` with one `file` part. Max 25 MB. Server stores the upload under `/srv/memex/data/uploads/<uuid><ext>` before inserting the queue row.

```json
// 202 Accepted
{"id": 4125, "status": "queued", "created_at": "..."}
```

`POST /captures/voice` — same shape as `/captures/file` but `Content-Type` of the part must match `audio/*`. The worker is responsible for transcription via whisper.cpp.

`GET /captures?status=queued&limit=50&cursor=<id>` — paginated list, newest first.

```json
// 200 OK
{"items": [ {"id": 4125, "status": "queued", "...": "..."} ],
 "next_cursor": 4100}
```

`GET /captures/{id}` — single row as a flat JSON object mirroring the SQL columns.

```json
// 200 OK
{"id": 4123, "status": "filed", "confidence": 0.87,
 "vault_path": "resources/ml-papers/2026-05-10--attention-is-all-you-need-redux.md",
 "...": "..."}

// 404 Not Found
{"error": {"code": "not_found", "message": "no queue item with id 4123"}}
```

## Worker contract

The worker is a single-threaded asyncio loop. It polls the queue every 5 seconds:

```sql
SELECT * FROM queue WHERE status = 'queued' ORDER BY created_at ASC LIMIT 10;
```

For each batch it:

1. Atomically claims the row with `UPDATE queue SET status='processing', updated_at=?, attempts=attempts+1 WHERE id=? AND status='queued'`. If the row count is 0, another instance won; skip.
2. Extracts content based on `source_type`:
   - `url`: trafilatura. YouTube URLs (host matches `youtube.com` / `youtu.be`) try `yt-dlp --write-auto-sub --skip-download --sub-lang en --convert-subs srt` first; on failure, fall back to trafilatura against the watch page; on second failure, route to `_inbox/` with `extraction_failed: true` in front-matter.
   - `file`: read bytes from `stored_path`. Text files are read as UTF-8; PDFs use `pypdf`; other binary formats are stored as attachments and referenced from a stub note.
   - `text`: pass through.
   - `voice`: whisper.cpp via subprocess (`whisper-cpp -m models/ggml-base.en.bin -f <path> -otxt`); the original audio is moved into `vault/_attachments/`.
3. Loads `vault/_meta/taxonomy.yml` and constructs the filing prompt from `worker/prompts/file.md`.
4. Shells out to `claude -p` with the prompt and the extracted content. The worker passes `--output-format json` and parses the response. The expected JSON shape is `{"folder": "<path>", "title": "<string>", "summary": "<string>", "tags": ["..."], "confidence": <float>}`.
5. Resolves routing using "Confidence thresholds & routing" below.
6. Writes the note to disk with front-matter, then updates the queue row in a single transaction:

```sql
UPDATE queue
   SET status = ?,             -- 'filed' | 'needs_review' | 'failed'
       updated_at = ?,
       processed_at = ?,
       confidence = ?,
       vault_path = ?,
       claude_session_id = ?,
       claude_input_tokens = ?,
       claude_output_tokens = ?,
       claude_duration_ms = ?,
       last_error = NULL
 WHERE id = ?;
```

Retry policy: transient failures (`claude -p` non-zero exit, network errors, whisper subprocess crashes) move the row back to `queued` with `last_error` set, up to `attempts = 5`. The 6th attempt sets `status='failed'`. Permanent failures (taxonomy validation error, oversized content, unsupported MIME) go straight to `failed`.

The worker never writes outside `vault/` and `/srv/memex/data/`. It never reads `claude -p` output that isn't valid JSON; on parse failure it logs `event="claude_response_invalid_json"` and treats it as a transient failure.

Batching: the worker processes at most 10 items per 5-second tick and sleeps an additional `MEMEX_WORKER_BATCH_PAUSE_SECONDS` (default 60) between ticks when the previous tick made any `claude -p` call. This is the system's only throttle for Claude Max session usage.

## Telegram bot contract

One bot token. Authorization is a chat-ID whitelist loaded from `MEMEX_TELEGRAM_ALLOWED_CHAT_IDS` (comma-separated). Messages from non-whitelisted chats are silently dropped with a debug log.

Commands:

| Command | Purpose |
| --- | --- |
| `/start` | Show one-line greeting and the command list. |
| `/help` | Same as `/start`. |
| `/queue` | Show counts by status for the last 24 h. |
| `/last` | Show the 5 most recent captures with their resolved `vault_path`. |
| `/find <query>` | Force retrieval intent regardless of message shape. |
| `/capture <text>` | Force capture intent regardless of message shape. |

Intent detection for non-command messages, **first match wins**:

1. Message contains a document, audio, voice, video, or photo attachment → **capture**.
2. Message text matches the URL regex `^\s*https?://\S+\s*$` (a single bare URL, optionally surrounded by whitespace) → **capture**.
3. Message text contains any URL alongside other text → **capture**, with the URL extracted and the rest stored as `user_note`.
4. Message text ends with `?` (after stripping trailing whitespace) → **retrieval**.
5. Message text starts with one of `who`, `what`, `when`, `where`, `why`, `how`, `which`, `find`, `show`, `recall`, `remind` (case-insensitive, word-boundary) → **retrieval**.
6. Otherwise → **capture** as `text`.

Capture acknowledgement (sent within 2 seconds of receipt):

```text
✓ Queued #4123 (url) — I'll let you know where it lands.
```

When the worker reaches `filed` or `needs_review`, the bot is **not** notified; the user sees results either via `/last` or via the dashboard. (The bot does not subscribe to queue events; this keeps it stateless.)

Retrieval answer rendering — see "Retrieval response schema" for the payload. The bot renders one Telegram message per logical section:

1. Message 1: the `answer` field, rendered as Markdown. If `answer` exceeds 3500 characters, split on paragraph boundaries into multiple messages, numbered `(1/n)`, `(2/n)`, …
2. Message 2: a "Sources" message listing each source as `• <vault_path>` on its own line.
3. Message 3: a "Quotes" message rendering each quote as a Telegram blockquote prefixed with the source's index.

If `sources` is empty, only Message 1 is sent and it ends with the literal line `_No sources found in vault._`.

## Retrieval response schema

`claude -p` is invoked by the Telegram bot and the dashboard with the prompt at `telegram_bot/prompts/retrieve.md` and `--output-format json`. The expected payload:

```json
{
  "answer": "Markdown-formatted answer to the user's question.",
  "sources": [
    {"path": "resources/ml-papers/2026-04-02--rope-scaling.md", "title": "RoPE scaling notes"},
    {"path": "areas/health/2026-03-19--sleep-experiment.md",   "title": "Sleep experiment week 3"}
  ],
  "quotes": [
    {"source_index": 0, "text": "Position interpolation degrades smoothly past 4× context."},
    {"source_index": 1, "text": "Magnesium glycinate dropped wake-after-sleep-onset by 18 min."}
  ],
  "confidence": 0.74
}
```

Field semantics:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `answer` | string | yes | Markdown. Empty string means "no answer found"; the renderer must still produce a message. |
| `sources` | array | yes (may be empty) | Vault-relative paths, no leading slash. Order is meaningful and stable for `quotes` indexing. |
| `sources[].path` | string | yes | Must exist on disk; the renderer warns if it does not. |
| `sources[].title` | string | yes | Front-matter title or filename stem. |
| `quotes` | array | yes (may be empty) | Each quote is at most 280 characters; longer quotes are an error and the renderer truncates with an ellipsis. |
| `quotes[].source_index` | int | yes | 0-based index into `sources`. |
| `quotes[].text` | string | yes | Verbatim from the source file. No markdown. |
| `confidence` | float | yes | `[0.0, 1.0]`. The renderer flags `confidence < 0.50` to the user. |

Renderer differences:

- **Telegram bot**: three separate messages as described in the bot contract; quotes rendered as `> ` blockquotes.
- **Dashboard**: a single chat bubble. Answer at top; sources as a horizontal chip row directly under the answer; quotes as a vertical list at the bottom, each linking to its source via the chip's index. Both surfaces show the `confidence` value as a small caption ("filed at 0.74 confidence").

## Confidence thresholds & routing

The worker compares the model's `confidence` against the thresholds resolved from `taxonomy.yml` (per-folder override if present, otherwise global):

| Confidence band | Action | `status` written | `vault_path` written to | Front-matter `needs_review` |
| --- | --- | --- | --- | --- |
| `>= autonomous_threshold` | File silently into matched folder. | `filed` | `<folder>/YYYY-MM-DD--<slug>.md` | `false` |
| `[review_threshold, autonomous_threshold)` | File into matched folder but flag for human review. | `needs_review` | `<folder>/YYYY-MM-DD--<slug>.md` | `true` |
| `< review_threshold` | Route to inbox; do not pretend to know the folder. | `needs_review` | `_inbox/YYYY-MM-DD--<slug>.md` | `true` |

Defaults if `taxonomy.yml` is missing values: `autonomous_threshold = 0.80`, `review_threshold = 0.60`. These same numbers are the only place they appear in code: every component imports them from `shared.memex_shared.taxonomy`.

## Error handling & logging

All components log structured JSON, one object per line, to stdout. Docker captures stdout per service, so logs surface via `docker compose logs <service>`.

Required fields on every line:

| Field | Type | Notes |
| --- | --- | --- |
| `ts` | string | ISO-8601 UTC with `Z` suffix, microsecond precision. |
| `service` | string | One of `capture_api`, `worker`, `telegram_bot`, `dashboard`. |
| `level` | string | `debug` \| `info` \| `warn` \| `error`. |
| `event` | string | snake_case event name, e.g. `capture_received`, `worker_item_filed`, `claude_call_completed`. |

Conditional fields:

| Field | When |
| --- | --- |
| `queue_item_id` | Any log line related to a queue row. |
| `duration_ms` | Any log line that closes a measured operation (HTTP request, `claude -p` call, extraction). |
| `error` | `level` is `warn` or `error`. Object: `{"type": "<exception class>", "message": "<short>"}`. Stack traces go to a separate `traceback` field. |
| `claude_session_id` | Any log line tied to a `claude -p` invocation. |

Secret-redaction rules — applied by `shared.memex_shared.logging` before serialization:

1. Any field whose key matches `(?i)token|secret|api[_-]?key|password|authorization` is replaced with `"***"`.
2. Telegram chat IDs are hashed (SHA-256, first 12 hex chars) and emitted as `submitter_hash`. The raw `chat_id` is never logged.
3. `source_payload.text` and the bytes of file/voice payloads are never logged. The capture API logs `source_payload_size_bytes` instead.

## Rate-limit accounting

Claude Max sessions are shared between the Pi (worker + Telegram retrieval) and the Mac (developer's own Claude Code sessions). The system cannot read Anthropic's quota directly; instead it accounts locally:

1. Every `claude -p` invocation is wrapped by `shared.memex_shared.claude.invoke()`, which records start time, end time, exit code, and the `claude_session_id` parsed from the response envelope.
2. The wrapper inserts a row into a `claude_calls` table:

```sql
CREATE TABLE claude_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT    NOT NULL,                  -- ISO-8601 UTC of call start
    service         TEXT    NOT NULL,                  -- 'worker' | 'telegram_bot' | 'dashboard'
    purpose         TEXT    NOT NULL,                  -- 'file' | 'retrieve'
    queue_item_id   INTEGER,                           -- nullable; only set for filing calls
    session_id      TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    duration_ms     INTEGER,
    exit_code       INTEGER NOT NULL
);

CREATE INDEX claude_calls_ts ON claude_calls (ts);
```

3. The worker's batching pause (default 60 s between non-empty ticks, see "Worker contract") is the only enforced throttle. There is no parallel fan-out: the worker processes items serially within a tick, and the Telegram bot serializes retrieval calls per chat.

4. The dashboard surfaces from this table:
   - calls per hour for the last 24 h, stacked by `service`,
   - tokens per hour for the last 24 h,
   - rolling 5-minute exit-code error rate,
   - last 20 calls in a table.

## Front-matter conventions

Every generated note carries this YAML front-matter, in this field order, with no extra fields:

```yaml
---
id: 4123                                  # int; matches queue.id
source: url                               # one of: url | file | text | voice
captured_at: 2026-05-10T14:22:01.123456Z  # mirrors queue.created_at
processed_at: 2026-05-10T14:23:18.998012Z # mirrors queue.processed_at
confidence: 0.87                          # mirrors queue.confidence
taxonomy_path: resources/ml-papers        # vault-relative folder, no leading slash
tags: [transformer, attention, paper]     # always a list, may be empty
needs_review: false                       # bool
original_url: https://example.com/x       # only when source == url
attachment: _attachments/<uuid>.ogg       # only when source in (file, voice)
---
```

`tags` are lower-case, kebab-cased, deduplicated, and sorted ascending. `taxonomy_path` is `_inbox` (no slash) when the note was inbox-routed. The body of the note follows: an H1 with the worker-derived title, then the model's `summary`, then the extracted content under an H2 `Source`.

## Versioning & change-control

This file carries `contract_version` in its YAML front-matter at the top (currently `1.0.0`). The version follows semver:

- **Patch** (`1.0.x`) — clarifications, typo fixes, prose edits that do not change a schema, name, or numeric default.
- **Minor** (`1.x.0`) — additive: new endpoint, new optional field, new enum value with a default.
- **Major** (`x.0.0`) — breaking: renamed field, removed endpoint, changed numeric default that components depend on.

Downstream components pin to a contract version in their package metadata (`memex_contract = "^1.0"` in `pyproject.toml`). On startup, each service reads `CLAUDE.md`'s front-matter and refuses to run if the major version does not match its pin. Bumping `contract_version` is the same PR as the change it describes; `Progress-Tracker.md` records the bump in the next phase entry.
