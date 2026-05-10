#!/usr/bin/env bash
# scripts/teardown.sh — stop the Memex stack and (optionally) reset state.
#
# Usage:
#   scripts/teardown.sh                         Stop the stack only.
#   scripts/teardown.sh --prune-images          Also remove the built images.
#   scripts/teardown.sh --reset-claude-login    Also remove the claude_auth volume.
#                                               Forces a fresh `claude /login`
#                                               on the next bootstrap.
#   scripts/teardown.sh --wipe-data             DESTRUCTIVE. Deletes the queue
#                                               database AND the vault. Two
#                                               confirmation prompts required.
#
# Flags compose; each is opt-in. The vault is the user's irreplaceable
# knowledge so we ask twice and never delete it without --wipe-data.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infra/docker-compose.yml"
ENV_FILE="${REPO_ROOT}/infra/.env"
LIB_DIR="${REPO_ROOT}/scripts/lib"

# shellcheck source=lib/prompt.sh
source "${LIB_DIR}/prompt.sh"

PRUNE_IMAGES=0
RESET_LOGIN=0
WIPE_DATA=0

for arg in "$@"; do
    case "$arg" in
        --prune-images)        PRUNE_IMAGES=1 ;;
        --reset-claude-login)  RESET_LOGIN=1 ;;
        --wipe-data)           WIPE_DATA=1 ;;
        -h|--help)
            sed -n '2,15p' "$0"; exit 0 ;;
        *) ui_die "unknown flag: $arg" ;;
    esac
done

if [[ ! -f "$ENV_FILE" ]]; then
    ui_warn "no $ENV_FILE found; running compose without env-file"
    COMPOSE=(docker compose -f "$COMPOSE_FILE")
else
    COMPOSE=(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE")
fi

ui_section "Stopping stack"
"${COMPOSE[@]}" down
ui_ok "stack stopped"

if (( PRUNE_IMAGES == 1 )); then
    ui_section "Removing built images"
    for img in memex/capture_api:latest memex/worker:latest memex/telegram_bot:latest; do
        if docker image inspect "$img" >/dev/null 2>&1; then
            docker image rm "$img" || ui_warn "failed to remove $img"
        fi
    done
    ui_ok "image prune complete"
fi

if (( RESET_LOGIN == 1 )); then
    ui_section "Removing claude_auth volume"
    cat >&2 <<'EOF'

This will delete the named volume `memex_claude_auth`. The next bootstrap
will require a fresh `claude /login`. The vault and the queue are NOT
touched by this operation.

EOF
    if ask_yn "Proceed?" "n"; then
        if docker volume inspect memex_claude_auth >/dev/null 2>&1; then
            docker volume rm memex_claude_auth
            ui_ok "claude_auth volume removed"
        else
            ui_info "claude_auth volume did not exist"
        fi
    else
        ui_info "claude_auth volume left intact"
    fi
fi

if (( WIPE_DATA == 1 )); then
    ui_section "DESTRUCTIVE: --wipe-data"
    if [[ ! -f "$ENV_FILE" ]]; then
        ui_die "cannot wipe without $ENV_FILE — paths unknown"
    fi
    # shellcheck disable=SC1090,SC1091
    { set -a; . "$ENV_FILE"; set +a; }
    cat >&2 <<EOF

WARNING: --wipe-data deletes the following directories outright:

    $MEMEX_VAULT_PATH        (your entire vault)
    $MEMEX_DATA_PATH         (queue.db + uploads)

This is unrecoverable. Confirm twice to proceed.

EOF
    if ! ask_yn "Type y to confirm step 1/2" "n"; then
        ui_info "aborted; nothing deleted"; exit 0
    fi
    if ! ask_yn "Confirm AGAIN — REALLY delete the vault and queue?" "n"; then
        ui_info "aborted; nothing deleted"; exit 0
    fi
    sudo rm -rf -- "$MEMEX_VAULT_PATH" "$MEMEX_DATA_PATH"
    ui_ok "wiped vault + data"
fi

ui_ok "teardown complete."
