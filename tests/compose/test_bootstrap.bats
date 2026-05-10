#!/usr/bin/env bats
# Bats tests for scripts/bootstrap.sh — runs in --dry-run mode so the suite
# touches no host directories and never invokes docker.

setup() {
    REPO_ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
    BOOTSTRAP="$REPO_ROOT/scripts/bootstrap.sh"
    LIB="$REPO_ROOT/scripts/lib"
}

@test "scripts/bootstrap.sh passes shellcheck" {
    if ! command -v shellcheck >/dev/null 2>&1; then
        skip "shellcheck not installed"
    fi
    run shellcheck \
        --severity=warning \
        -x \
        -P "$LIB" \
        "$REPO_ROOT/scripts/bootstrap.sh" \
        "$REPO_ROOT/scripts/teardown.sh" \
        "$LIB/prompt.sh" \
        "$LIB/claude_login.sh"
    [ "$status" -eq 0 ]
}

@test "bootstrap rejects an obviously invalid telegram token in --dry-run" {
    if [ "$(id -u)" -eq 0 ]; then
        skip "bootstrap refuses to run as root; run this test as a non-root user"
    fi
    # Inputs in order before the bot token: vault, data, syncthing, poll,
    # pause, model, tz. Then an invalid token; the script re-prompts and
    # dies when stdin closes.
    run bash -c "$BOOTSTRAP --dry-run <<'EOF'
/srv/memex/vault
/srv/memex/data
/srv/memex/syncthing
5
60
ggml-base.en.bin
UTC
not-a-token
EOF"
    [ "$status" -ne 0 ]
    [[ "$output" == *"doesn't look like a BotFather token"* ]]
}

@test "bootstrap accepts a valid telegram token (dry-run, full happy path)" {
    if [ "$(id -u)" -eq 0 ]; then
        skip "bootstrap refuses to run as root; run this test as a non-root user"
    fi
    # Inputs in order:
    #   vault path, data path, syncthing path, poll, pause, model,
    #   tz, bot token, chat ids
    run bash -c "$BOOTSTRAP --dry-run <<'EOF'
/srv/memex/vault
/srv/memex/data
/srv/memex/syncthing
5
60
ggml-base.en.bin
UTC
12345678:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij
42
EOF"
    [ "$status" -eq 0 ]
    [[ "$output" == *"dry run OK"* ]]
}

@test "bootstrap rejects a non-absolute vault path" {
    if [ "$(id -u)" -eq 0 ]; then
        skip "bootstrap refuses to run as root; run this test as a non-root user"
    fi
    run bash -c "$BOOTSTRAP --dry-run <<'EOF'
relative/path
/srv/memex/data
/srv/memex/syncthing
EOF"
    [ "$status" -ne 0 ]
    [[ "$output" == *"path must be absolute"* ]]
}

@test "bootstrap refuses to run as root" {
    if [ "$(id -u)" -ne 0 ]; then
        skip "must run this assertion as root to test the refusal"
    fi
    run bash "$BOOTSTRAP" --dry-run
    [ "$status" -ne 0 ]
    [[ "$output" == *"do not run as root"* ]]
}

@test "bootstrap rejects unknown flag" {
    run bash "$BOOTSTRAP" --bogus
    [ "$status" -ne 0 ]
    [[ "$output" == *"unknown flag"* ]]
}
