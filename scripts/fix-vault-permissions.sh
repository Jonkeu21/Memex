#!/usr/bin/env bash
# scripts/fix-vault-permissions.sh — repair vault filesystem ownership / mode.
#
# The worker, telegram_bot, and dashboard containers run as uid 10001 (the
# in-image `memex` user, hardcoded in worker/Dockerfile:48-49). The vault on
# the host must therefore be owned by uid 10001 with the host operator's gid
# (MEMEX_GID, typically 1000) as the group, and have SGID set on dirs so
# worker-written files inherit that gid. The compose file adds MEMEX_GID as a
# supplementary group to those three services, letting Syncthing
# (PUID/PGID=MEMEX_GID), the host operator, and the worker all coexist on the
# same tree.
#
# This script is idempotent: it reapplies the correct ownership and mode and
# nothing else. No files are deleted or moved. Run it after a bootstrap that
# predates the permissions fix, or any time a stat shows the vault in an
# unexpected state.
#
# Usage:
#   scripts/fix-vault-permissions.sh           Use VAULT_PATH from infra/.env.
#   scripts/fix-vault-permissions.sh /path     Repair the given path instead.

set -euo pipefail

readonly MEMEX_WORKER_UID=10001
readonly DIR_MODE=2770
readonly FILE_MODE=0660

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/infra/.env"

die() { echo "fix-vault-permissions: $*" >&2; exit 1; }
info() { echo "fix-vault-permissions: $*"; }

vault_path="${1:-}"
if [[ -z "$vault_path" ]]; then
    [[ -f "$ENV_FILE" ]] || die "missing $ENV_FILE; pass the vault path as an argument"
    # shellcheck disable=SC1090
    vault_path="$(grep -E '^MEMEX_VAULT_PATH=' "$ENV_FILE" | cut -d= -f2-)"
    [[ -n "$vault_path" ]] || die "MEMEX_VAULT_PATH not set in $ENV_FILE"
fi
[[ -d "$vault_path" ]] || die "vault path $vault_path does not exist"

host_gid="$(id -g)"
if [[ -f "$ENV_FILE" ]]; then
    env_gid="$(grep -E '^MEMEX_GID=' "$ENV_FILE" | cut -d= -f2- || true)"
    if [[ -n "$env_gid" && "$env_gid" != "$host_gid" ]]; then
        info "warning: MEMEX_GID=$env_gid in $ENV_FILE differs from current gid $host_gid; using $env_gid"
        host_gid="$env_gid"
    fi
fi

info "vault: $vault_path"
info "owner -> ${MEMEX_WORKER_UID}:${host_gid}"
info "dirs  -> mode ${DIR_MODE} (drwxrws---)"
info "files -> mode ${FILE_MODE} (rw-rw----)"

sudo chown -R "${MEMEX_WORKER_UID}:${host_gid}" "$vault_path"
sudo find "$vault_path" -type d -exec chmod "$DIR_MODE" {} +
sudo find "$vault_path" -type f -exec chmod "$FILE_MODE" {} +

info "done"
