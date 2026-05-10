# Capture API

FastAPI service that validates inbound captures (URL, text, file, voice) and
enqueues them in the shared SQLite queue. The worker picks them up later;
this service does not classify or call Claude.

See [`/CLAUDE.md`](../CLAUDE.md) for the binding contract — schemas,
endpoint paths, status enums, and log fields are normative there.

## Local development

```bash
cd capture_api
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

export MEMEX_CAPTURE_TOKEN_dev=dev-token
export CAPTURE_DB_PATH=/tmp/memex/queue.db
export CAPTURE_INBOX_DIR=/tmp/memex/inbox

uvicorn app.main:create_app --factory --reload --port 8001
```

## Tests

```bash
pytest                # runs with coverage; CI gates at >= 90%
pytest -k auth        # subset
```

## Configuration (env vars only)

| Var | Default | Notes |
| --- | --- | --- |
| `MEMEX_CAPTURE_TOKEN_<LABEL>` | (none) | At least one required. `<LABEL>` is recorded as `submitter = "api:<label>"`. |
| `CAPTURE_DB_PATH` | `/data/queue.db` | SQLite file. WAL mode is enabled at startup. |
| `CAPTURE_INBOX_DIR` | `/data/inbox` | Files and voice uploads land under `<dir>/YYYY/MM/DD/<uuid>__<name>`. |
| `CAPTURE_MAX_UPLOAD_MB` | `25` | Larger uploads return 413 with no row written. |
| `CAPTURE_BIND_HOST` | `0.0.0.0` | |
| `CAPTURE_BIND_PORT` | `8001` | |
| `LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARN`/`ERROR`. |

We use `sqlite3` from the stdlib (not an ORM, not `aiosqlite`). The schema
is small and FastAPI's threadpool handles the synchronous calls fine on a
single-user system.

## Curl recipes

Set `TOKEN=...` to one of the configured tokens.

```bash
# URL
curl -fsS -X POST http://localhost:8001/captures/url \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/article","user_note":"skim later"}'

# Text
curl -fsS -X POST http://localhost:8001/captures/text \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"text":"raw body here"}'

# File
curl -fsS -X POST http://localhost:8001/captures/file \
  -H "Authorization: Bearer $TOKEN" -F file=@./scan.pdf

# Voice (audio/* required)
curl -fsS -X POST http://localhost:8001/captures/voice \
  -H "Authorization: Bearer $TOKEN" -F file=@./voice.ogg

# Queue listing
curl -fsS "http://localhost:8001/captures?status=queued&source_type=url&limit=20" \
  -H "Authorization: Bearer $TOKEN"

# Single
curl -fsS http://localhost:8001/captures/4123 -H "Authorization: Bearer $TOKEN"

# Health / readiness
curl -fsS http://localhost:8001/healthz
curl -fsS http://localhost:8001/readyz -H "Authorization: Bearer $TOKEN"
```
