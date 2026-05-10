#!/usr/bin/env bash
# scripts/bootstrap.sh — interactive, idempotent first-time setup for the
# Memex stack on a Raspberry Pi 5. Runs over SSH; expects no GUI.
#
# Usage:
#   scripts/bootstrap.sh                Interactive setup. Refuses to overwrite an existing .env.
#   scripts/bootstrap.sh --force        Allow overwriting an existing .env (backed up first).
#   scripts/bootstrap.sh --dry-run      Validate inputs only; touch nothing on disk; do not run docker.
#   scripts/bootstrap.sh --skip-login   Skip the claude /login step (useful if already logged in).
#
# Steps:
#   1. Refuse to run as root; sanity-check arch + Docker.
#   2. Detect existing .env and offer reconfigure / re-login / nothing.
#   3. Prompt for Telegram token, chat IDs, host paths, tunables.
#   4. Generate the capture API token via openssl rand -hex 32.
#   5. Create host directories with `sudo mkdir -p` + chown (only step that uses sudo).
#   6. Write infra/.env from infra/.env.example.
#   7. docker compose build.
#   8. Run `claude /login` headlessly via a one-shot worker container.
#   9. docker compose up -d.
#  10. Health-poll capture_api, send a "bootstrap-ok" self-test capture.
#  11. Print operator summary.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIB_DIR="${REPO_ROOT}/scripts/lib"
COMPOSE_FILE="${REPO_ROOT}/infra/docker-compose.yml"
ENV_FILE="${REPO_ROOT}/infra/.env"
ENV_EXAMPLE="${REPO_ROOT}/infra/.env.example"

# shellcheck source=lib/prompt.sh
source "${LIB_DIR}/prompt.sh"
# shellcheck source=lib/claude_login.sh
source "${LIB_DIR}/claude_login.sh"

DRY_RUN=0
FORCE=0
SKIP_LOGIN=0

for arg in "$@"; do
    case "$arg" in
        --dry-run)     DRY_RUN=1 ;;
        --force)       FORCE=1 ;;
        --skip-login)  SKIP_LOGIN=1 ;;
        -h|--help)
            sed -n '2,16p' "$0"
            exit 0
            ;;
        *) ui_die "unknown flag: $arg" ;;
    esac
done

COMPOSE=(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE")

# ─── Step 1: pre-flight ──────────────────────────────────────────────────────

ui_section "Pre-flight checks"

# Refuse root: the docker socket call doesn't need it, and host bind-mounts
# need to be owned by the operator's uid so Syncthing on the Mac sees them.
if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    ui_die "do not run as root; run as the Pi user that owns the vault"
fi

# Architecture check.
ARCH="$(uname -m)"
if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" ]]; then
    ui_warn "expected aarch64/arm64 (Raspberry Pi 5 64-bit), got: $ARCH"
    if (( DRY_RUN == 0 )); then
        ask_yn "Proceed anyway?" "n" || ui_die "aborted on architecture mismatch"
    fi
fi
ui_ok "architecture: $ARCH"

# Docker Engine + Compose plugin presence. Skipped in --dry-run so the
# bats tests don't require a working docker daemon.
if (( DRY_RUN == 0 )); then
    if ! command -v docker >/dev/null 2>&1; then
        ui_die "docker is not installed; see docs/deployment.md (OS prep)"
    fi
    if ! docker compose version >/dev/null 2>&1; then
        ui_die "docker compose plugin is not installed; see docs/deployment.md"
    fi
    if ! docker info >/dev/null 2>&1; then
        ui_die "cannot reach the Docker daemon; is your user in the docker group?"
    fi
    ui_ok "docker engine + compose plugin reachable"
else
    ui_info "skipping docker checks (--dry-run)"
fi

# openssl for the API token.
if ! command -v openssl >/dev/null 2>&1; then
    ui_die "openssl is required to generate the capture API token; apt install openssl"
fi

# ─── Step 2: detect existing setup ──────────────────────────────────────────

EXISTING=0
if [[ -f "$ENV_FILE" ]]; then
    EXISTING=1
fi

if (( EXISTING == 1 )); then
    ui_section "Existing setup detected"
    ui_info "found $ENV_FILE"
    cat >&2 <<'EOF'

Memex looks like it was already bootstrapped on this host. Choose:

  reconfigure     Re-prompt for everything and rewrite .env (backed up first).
                  Vault, queue, and claude login state are preserved.
  re-login        Skip the prompts and just re-run the claude /login flow.
  nothing         Exit without changes.
EOF
    CHOICE="$(ask "What would you like to do? (reconfigure | re-login | nothing)" "nothing" "")"
    case "$CHOICE" in
        reconfigure)
            FORCE=1
            ;;
        re-login)
            if (( DRY_RUN == 1 )); then
                ui_die "--dry-run cannot run claude /login"
            fi
            if claude_login_run "${COMPOSE[@]}"; then
                ui_ok "Re-login complete."
                exit 0
            else
                exit 1
            fi
            ;;
        nothing|"")
            ui_ok "No changes made. Exiting."
            exit 0
            ;;
        *)
            ui_die "unknown choice: $CHOICE"
            ;;
    esac
fi

# ─── Step 3: gather configuration ───────────────────────────────────────────

ui_section "Configuration"

VAULT_PATH="$(ask "Vault host path"   "/srv/memex/vault"     validate_abs_path)"
DATA_PATH="$(ask "Data host path (queue.db + uploads)" "/srv/memex/data" validate_abs_path)"
SYNCTHING_CONFIG="$(ask "Syncthing config path" "/srv/memex/syncthing" validate_abs_path)"

POLL_SECONDS="$(ask "Worker poll interval (seconds)" "5"   validate_positive_int)"
PAUSE_SECONDS="$(ask "Worker batch pause (seconds, throttles claude calls)" "300" validate_positive_int)"

WHISPER_MODEL="$(ask "Whisper model file (ggml-tiny.en.bin or ggml-base.en.bin)" "ggml-base.en.bin" validate_whisper_model)"

TZ_VALUE="$(ask "Container timezone (IANA, e.g. America/Los_Angeles)" "$(cat /etc/timezone 2>/dev/null || echo UTC)" "")"

ui_section "Telegram"

BOT_TOKEN="$(ask "BotFather token" "" validate_telegram_token)"

cat >&2 <<'EOF'

Allowed chat IDs are the integer IDs of the Telegram chats this bot will
respond to. Multiple IDs are comma-separated (e.g. "12345,-9876").
You can leave this blank for now and add IDs later by editing infra/.env;
the bot will reject every message until at least one ID is listed.

EOF
CHAT_IDS="$(ask "Allowed chat IDs (comma-separated)" "" validate_chat_ids)"
if [[ -z "$CHAT_IDS" ]]; then
    ui_warn "no chat IDs set: the bot will silently drop all messages until you add one."
fi

# Generated, never prompted.
CAPTURE_TOKEN="$(openssl rand -hex 32)"
DASHBOARD_TOKEN="$(openssl rand -hex 32)"

# Use the running user's uid/gid for Syncthing.
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

if (( DRY_RUN == 1 )); then
    ui_section "Dry run summary"
    cat >&2 <<EOF
  vault_path:       $VAULT_PATH
  data_path:        $DATA_PATH
  syncthing_config: $SYNCTHING_CONFIG
  poll_seconds:     $POLL_SECONDS
  pause_seconds:    $PAUSE_SECONDS
  whisper_model:    $WHISPER_MODEL
  tz:               $TZ_VALUE
  chat_ids:         ${CHAT_IDS:-(none)}
  uid/gid:          $HOST_UID/$HOST_GID
  capture_token:    [redacted, 64 hex chars]
  dashboard_token:  [redacted, 64 hex chars]
  bot_token:        [redacted, accepted]
  Would write:      $ENV_FILE
  Would NOT run:    docker compose build/up, claude /login
EOF
    ui_ok "dry run OK"
    exit 0
fi

# ─── Step 4: host directories ───────────────────────────────────────────────

ui_section "Host directories"

create_dir() {
    local p="$1"
    if [[ -d "$p" ]]; then
        ui_info "exists: $p"
        return 0
    fi
    ui_info "creating $p (will prompt for sudo)"
    sudo mkdir -p "$p"
    sudo chown "$HOST_UID:$HOST_GID" "$p"
    sudo chmod 750 "$p"
}
create_dir "$VAULT_PATH"
create_dir "$DATA_PATH"
create_dir "$SYNCTHING_CONFIG"
mkdir -p "$DATA_PATH/uploads"

# ─── Step 5: write infra/.env ───────────────────────────────────────────────

ui_section "Writing $ENV_FILE"

if [[ -f "$ENV_FILE" ]]; then
    if (( FORCE == 0 )); then
        ui_die "$ENV_FILE exists; rerun with --force to overwrite (existing file backed up)"
    fi
    BACKUP="${ENV_FILE}.bak.$(date -u +%Y%m%dT%H%M%SZ)"
    cp "$ENV_FILE" "$BACKUP"
    ui_info "backed up existing .env → $BACKUP"
fi

if [[ ! -f "$ENV_EXAMPLE" ]]; then
    ui_die "missing $ENV_EXAMPLE"
fi

# Build the file from scratch rather than sed-substituting the example, so
# every value is explicit and reviewable in plain text.
umask 077
cat > "$ENV_FILE" <<EOF
# Generated by scripts/bootstrap.sh — $(date -u +%Y-%m-%dT%H:%M:%SZ)
MEMEX_VAULT_PATH=$VAULT_PATH
MEMEX_DATA_PATH=$DATA_PATH
MEMEX_SYNCTHING_CONFIG=$SYNCTHING_CONFIG
MEMEX_UID=$HOST_UID
MEMEX_GID=$HOST_GID
TZ=$TZ_VALUE

MEMEX_CAPTURE_TOKEN_telegram=$CAPTURE_TOKEN
MEMEX_CAPTURE_MAX_UPLOAD_MB=25

MEMEX_WORKER_POLL_SECONDS=$POLL_SECONDS
MEMEX_WORKER_BATCH_PAUSE_SECONDS=$PAUSE_SECONDS
MEMEX_WORKER_BATCH_MAX=10
MEMEX_WORKER_MAX_ATTEMPTS=5
MEMEX_WORKER_CLAUDE_TIMEOUT_SECONDS=180
MEMEX_WHISPER_MODEL_FILE=$WHISPER_MODEL

MEMEX_TELEGRAM_BOT_TOKEN=$BOT_TOKEN
MEMEX_TELEGRAM_ALLOWED_CHAT_IDS=$CHAT_IDS
MEMEX_TELEGRAM_CLAUDE_TIMEOUT_SECONDS=120
MEMEX_TELEGRAM_MAX_DOWNLOAD_MB=25

MEMEX_DASHBOARD_BEARER_TOKEN=$DASHBOARD_TOKEN
MEMEX_DASHBOARD_CLAUDE_TIMEOUT_SECONDS=120

MEMEX_LOG_LEVEL=INFO
EOF
chmod 600 "$ENV_FILE"
ui_ok "wrote $ENV_FILE (mode 600)"

# ─── Step 6: build images ───────────────────────────────────────────────────

ui_section "Building images (this is the long one)"
"${COMPOSE[@]}" build
ui_ok "images built"

# ─── Step 7: claude /login ──────────────────────────────────────────────────

if (( SKIP_LOGIN == 1 )); then
    ui_warn "skipping claude /login per --skip-login"
elif claude_login_present "${COMPOSE[@]}"; then
    ui_info "claude_auth volume already contains credentials — skipping login"
    ui_info "(rerun with --force to reconfigure or use scripts/teardown.sh --reset-claude-login to start over)"
else
    if ! claude_login_run "${COMPOSE[@]}"; then
        ui_die "claude /login failed; rerun bootstrap.sh after fixing the issue"
    fi
fi

# ─── Step 8: bring up the stack ─────────────────────────────────────────────

ui_section "Starting the stack"
"${COMPOSE[@]}" up -d
ui_ok "compose up returned"

ui_info "waiting for capture_api to report healthy..."
DEADLINE=$(( $(date +%s) + 60 ))
while true; do
    STATUS="$("${COMPOSE[@]}" ps --format json capture_api 2>/dev/null | grep -o '"Health":"[^"]*"' | head -n1 | sed 's/.*:"//;s/"$//' || true)"
    if [[ "$STATUS" == "healthy" ]]; then
        break
    fi
    if (( $(date +%s) > DEADLINE )); then
        ui_warn "capture_api did not report healthy within 60s; check 'docker compose logs capture_api'"
        break
    fi
    sleep 2
done
ui_ok "capture_api status: ${STATUS:-unknown}"

# ─── Step 9: self-test capture ──────────────────────────────────────────────

ui_section "Self-test capture"
SELFTEST_RESPONSE="$(
    "${COMPOSE[@]}" exec -T capture_api python -c "
import json, urllib.request
req = urllib.request.Request(
    'http://127.0.0.1:8001/captures/text',
    data=json.dumps({'text': 'bootstrap-ok'}).encode(),
    headers={
        'Authorization': 'Bearer ${CAPTURE_TOKEN}',
        'Content-Type': 'application/json',
    },
    method='POST',
)
with urllib.request.urlopen(req) as r:
    print(r.read().decode())
" 2>&1
)" || true
if [[ "$SELFTEST_RESPONSE" == *'"status":"queued"'* ]]; then
    ui_ok "self-test capture accepted: $SELFTEST_RESPONSE"
else
    ui_warn "self-test capture did NOT return queued status:"
    ui_warn "$SELFTEST_RESPONSE"
fi

# ─── Step 10: operator summary ──────────────────────────────────────────────

cat >&2 <<EOF

──── Done ────

Stack is running. Useful commands:

  docker compose -f infra/docker-compose.yml ps
  docker compose -f infra/docker-compose.yml logs -f worker
  docker compose -f infra/docker-compose.yml logs -f telegram_bot

Adding a chat ID later (no restart of capture/worker required):

  edit  infra/.env  # set MEMEX_TELEGRAM_ALLOWED_CHAT_IDS=<id1>,<id2>
  docker compose -f infra/docker-compose.yml up -d telegram_bot

Vault is at:        $VAULT_PATH      (Syncthing's canonical copy)
Queue + uploads:    $DATA_PATH
Syncthing UI:       ssh -L 8384:127.0.0.1:8384 <pi-host>  →  http://127.0.0.1:8384
Claude login state: docker volume "memex_claude_auth"

Dashboard:          http://<pi-tailscale-host>:8002/
                    Paste this token into the dashboard's Settings drawer:
                    $DASHBOARD_TOKEN

EOF
ui_ok "bootstrap complete."
