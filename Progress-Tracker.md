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
