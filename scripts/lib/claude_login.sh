#!/usr/bin/env bash
# scripts/lib/claude_login.sh — the headless `claude login` dance.
# Sourced, never executed.

# shellcheck shell=bash
# shellcheck source=./prompt.sh
# (sourced after prompt.sh by the parent)

# Run an interactive `claude /login` inside a one-shot worker container so the
# auth state lands in the shared `claude_auth` named volume. The Claude Code
# CLI prints a URL the user opens on their laptop; the user signs in, copies
# the resulting code back, and pastes it at the prompt the CLI shows in the
# terminal.
#
# We deliberately use `docker compose run --rm` rather than `docker run` so
# the Compose project's volumes/network are reused — that means the same
# `claude_auth` volume the running services will use.
#
# Implementation notes:
#   * We attach a TTY (`-T` is OFF; the default Compose behaviour gives us a
#     TTY when stdout is a TTY).
#   * We pass /usr/local/bin/claude explicitly so the test that the binary is
#     present is part of this step.
#   * We set HOME=/home/memex in the override-environment so `claude` writes
#     credentials to /home/memex/.claude/credentials.json — exactly where the
#     `claude_auth` volume is mounted.

claude_login_run() {
    local compose=("$@")
    ui_section "Claude Code CLI login"
    cat >&2 <<'EOF'

Memex shells out to `claude -p` for filing and retrieval. The CLI must be
authenticated against your Claude Max account. You only need to do this once
per Pi: the credentials live in the named volume `memex_claude_auth` and are
shared between the worker and the Telegram bot.

What's about to happen:

  1. Memex starts a one-shot container from the worker image.
  2. The Claude Code CLI prints a URL plus a one-time code.
  3. You open that URL in a browser on your laptop (NOT the Pi — it's headless),
     sign in to your Anthropic account, and Anthropic shows you a code.
  4. You paste the code back into the terminal.
  5. The CLI writes ~/.claude/credentials.json into the named volume and exits.

If your terminal can't read the URL clearly, the CLI also writes it to its
own log; copy from there. If the code has expired, just rerun this script and
you'll get a fresh one.

EOF

    if ! ask_yn "Ready to start the login flow?" "y"; then
        ui_die "aborted at operator request"
    fi

    # The worker image's entrypoint is `tini`; we override to bypass it for
    # the interactive subcommand. `--rm` cleans up the container afterwards.
    if ! "${compose[@]}" run --rm --no-deps \
            --entrypoint /usr/local/bin/claude \
            worker /login; then
        ui_warn "claude /login exited non-zero"
        ui_warn "If the device-code expired, rerun: scripts/bootstrap.sh"
        return 1
    fi

    ui_ok "Login flow exited successfully. Verifying with a no-op call..."
    if ! "${compose[@]}" run --rm --no-deps \
            --entrypoint /usr/local/bin/claude \
            worker -p --output-format json "ping" >/dev/null; then
        ui_warn "claude -p smoke test failed."
        ui_warn "Common causes:"
        ui_warn "  • paste step was skipped → rerun bootstrap"
        ui_warn "  • Claude Max session quota exhausted → wait + rerun"
        ui_warn "  • network egress blocked → check Pi DNS / Tailscale ACLs"
        return 1
    fi
    ui_ok "claude CLI is authenticated and reachable."
    return 0
}

# Returns 0 if the named claude_auth volume contains a credentials file —
# i.e. login has already been done. Best-effort: missing volume returns 1.
claude_login_present() {
    local compose=("$@")
    "${compose[@]}" run --rm --no-deps \
        --entrypoint sh \
        worker -c 'test -s /home/memex/.claude/credentials.json' \
        >/dev/null 2>&1
}
