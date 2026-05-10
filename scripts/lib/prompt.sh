#!/usr/bin/env bash
# scripts/lib/prompt.sh — input + validation helpers for bootstrap.sh.
# Sourced, never executed.

# shellcheck shell=bash

# Print a heading to stderr with a divider above it.
ui_section() {
    printf '\n──── %s ────\n' "$1" >&2
}

# Print an info message to stderr.
ui_info() {
    printf 'ℹ %s\n' "$1" >&2
}

# Print a warning to stderr.
ui_warn() {
    printf '⚠ %s\n' "$1" >&2
}

# Print an error to stderr and exit 1.
ui_die() {
    printf '✗ %s\n' "$1" >&2
    exit 1
}

# Print a success line to stderr.
ui_ok() {
    printf '✓ %s\n' "$1" >&2
}

# Read a value from the operator with a default + optional validator.
# Usage: ask "Prompt text" "default value" validator_fn   (validator may be empty)
# Echoes the validated value on stdout. Re-prompts on validation failure.
ask() {
    local prompt="$1" default="$2" validator="${3:-}" answer=""
    while true; do
        if [[ -n "$default" ]]; then
            printf '%s [%s]: ' "$prompt" "$default" >&2
        else
            printf '%s: ' "$prompt" >&2
        fi
        if ! IFS= read -r answer; then
            ui_die "stdin closed; aborting"
        fi
        if [[ -z "$answer" ]]; then
            answer="$default"
        fi
        if [[ -z "$validator" ]] || "$validator" "$answer"; then
            printf '%s' "$answer"
            return 0
        fi
    done
}

# Yes/no prompt. Default is supplied as "y" or "n". Returns 0 for yes, 1 for no.
ask_yn() {
    local prompt="$1" default="${2:-n}" answer=""
    local hint
    if [[ "$default" == "y" ]]; then hint="Y/n"; else hint="y/N"; fi
    while true; do
        printf '%s [%s]: ' "$prompt" "$hint" >&2
        if ! IFS= read -r answer; then
            ui_die "stdin closed; aborting"
        fi
        answer="${answer:-$default}"
        case "$answer" in
            y|Y|yes|YES) return 0 ;;
            n|N|no|NO)   return 1 ;;
            *) ui_warn "answer y or n" ;;
        esac
    done
}

# Validators — return 0 on success, 1 on failure (with a warning printed).

validate_telegram_token() {
    local v="$1"
    if [[ "$v" =~ ^[0-9]+:[A-Za-z0-9_-]{30,}$ ]]; then
        return 0
    fi
    ui_warn "doesn't look like a BotFather token (expected <digits>:<35+ chars>)"
    return 1
}

validate_chat_ids() {
    local v="$1"
    # Allow empty (operator chose to defer adding a chat id).
    if [[ -z "$v" ]]; then
        return 0
    fi
    local IFS=',' part
    for part in $v; do
        part="${part// /}"
        if [[ -z "$part" ]]; then
            continue
        fi
        if ! [[ "$part" =~ ^-?[0-9]+$ ]]; then
            ui_warn "chat id $part is not an integer"
            return 1
        fi
    done
    return 0
}

validate_abs_path() {
    local v="$1"
    if [[ "$v" == /* ]]; then
        return 0
    fi
    ui_warn "path must be absolute (start with /)"
    return 1
}

validate_positive_int() {
    local v="$1"
    if [[ "$v" =~ ^[0-9]+$ ]] && (( v > 0 )); then
        return 0
    fi
    ui_warn "must be a positive integer"
    return 1
}

validate_whisper_model() {
    local v="$1"
    case "$v" in
        ggml-tiny.en.bin|ggml-base.en.bin) return 0 ;;
    esac
    ui_warn "expected ggml-tiny.en.bin or ggml-base.en.bin"
    return 1
}
