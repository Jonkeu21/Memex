# Memex Telegram bot

Single-process bot that bridges a Telegram chat with the Memex stack:

- **Captures** (URLs, files, voice/audio, documents, photos, plain text) are
  forwarded to the capture API as HTTP POSTs.
- **Retrievals** (questions over the vault) shell out to `claude -p` with the
  vault directory as context, parse the JSON envelope, and render the
  answer + sources + quotes as three Telegram messages.

The bot is the only component allowed to make outbound calls to the public
internet. It uses **long polling** against `api.telegram.org`, not webhooks.

## Contracts

This service obeys `CLAUDE.md` at the repo root for:

- the command set (`/start`, `/help`, `/queue`, `/last`, `/find`, `/capture`),
- the ordered intent-detection ruleset,
- the capture API surface (`/captures/{url,text,file,voice}`),
- the retrieval JSON envelope and the three-message render shape,
- log format, redaction rules, and `claude_calls` telemetry.

If `CLAUDE.md` and this README disagree, `CLAUDE.md` wins.

## Configuration

All config is via environment variables.

| Var | Default | Purpose |
| --- | --- | --- |
| `MEMEX_TELEGRAM_BOT_TOKEN` | — (required) | Telegram bot token from BotFather. |
| `MEMEX_TELEGRAM_ALLOWED_CHAT_IDS` | — (required) | Comma-separated list of chat IDs allowed to talk to the bot. Anyone else is silently ignored. |
| `MEMEX_CAPTURE_API_BASE_URL` | `http://capture_api:8001` | URL of the capture API inside Compose. |
| `MEMEX_CAPTURE_API_TOKEN` | — (required) | Bearer token value (the value of `MEMEX_CAPTURE_TOKEN_telegram` configured in the capture API). |
| `MEMEX_TELEGRAM_VAULT_DIR` | `/vault` | Bind-mounted vault directory passed into the retrieval prompt. |
| `MEMEX_TELEGRAM_DB_PATH` | `/srv/memex/data/memex.db` | Bind-mounted SQLite path used for `/queue` and `/last` (read-only) and `claude_calls` writes. |
| `MEMEX_TELEGRAM_CLAUDE_BIN` | `claude` | Path to the Claude Code CLI binary. |
| `MEMEX_TELEGRAM_CLAUDE_TIMEOUT_SECONDS` | `120` | Hard timeout on each `claude -p` invocation. |
| `MEMEX_TELEGRAM_MAX_DOWNLOAD_MB` | `25` | Reject Telegram attachments larger than this before downloading. |
| `MEMEX_LOG_LEVEL` | `INFO` | Standard Python log levels (`DEBUG`/`INFO`/`WARNING`/`ERROR`). |

## Adding a chat ID to the whitelist

1. Send any message from your Telegram account to the bot. It will be silently dropped.
2. Read the structured-log line `event=chat_rejected` — it contains a hashed
   `submitter_hash`. To get the raw chat ID instead, talk to
   [`@userinfobot`](https://t.me/userinfobot) on Telegram.
3. Add the chat ID to `MEMEX_TELEGRAM_ALLOWED_CHAT_IDS` (comma-separated)
   in `infra/.env`, then `docker compose up -d telegram_bot`.

## Local development

```bash
cd telegram_bot
pip install -e .[dev]
pytest                 # 110 tests, 87% coverage
```

The test suite uses fakes for python-telegram-bot's `Update`/`Message`
hierarchy and `httpx.MockTransport` for the capture API. `subprocess.run` for
`claude -p` is replaced by an injectable callable on every test path.

To smoke-test against a real bot:

```bash
export MEMEX_TELEGRAM_BOT_TOKEN=...
export MEMEX_TELEGRAM_ALLOWED_CHAT_IDS=123456789
export MEMEX_CAPTURE_API_BASE_URL=http://localhost:8001
export MEMEX_CAPTURE_API_TOKEN=$(grep MEMEX_CAPTURE_TOKEN_telegram ../infra/.env | cut -d= -f2-)
export MEMEX_TELEGRAM_DB_PATH=/tmp/memex.db        # or wherever the API writes
export MEMEX_TELEGRAM_VAULT_DIR=/tmp/vault
python -m bot.main
```

## Container build

```bash
docker buildx build --platform linux/arm64 -t memex/telegram-bot .
```

The image is base Python 3.11-slim. The Claude Code CLI binary is **not**
bundled — Compose mounts the host's `claude` (and its session state) into
`/usr/local/bin/claude`. See `infra/docker-compose.yml` (Phase 5).

## Wire diagram

```
Telegram ──poll──► bot ──┬─► POST /captures/...       (capture API)
                         └─► subprocess `claude -p`   (retrieval, vault as ctx)
                              └─► insert claude_calls (SQLite, telemetry)
```
