"""Compose-file shape tests.

Drives `docker compose config` against a synthetic .env so the suite is
self-contained and runs anywhere docker is installed. Asserts the structural
constraints listed in scripts/bootstrap.sh and CLAUDE.md.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "infra" / "docker-compose.yml"


def _have_docker() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            check=True,
            capture_output=True,
            timeout=10,
        )
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _have_docker(), reason="docker compose plugin not available"
)


@pytest.fixture(scope="module")
def synthetic_env(tmp_path_factory) -> Path:
    # Compose evaluates env_file: paths at parse time. The compose file
    # declares env_file: ./.env (relative to the compose file's directory),
    # so we have to materialise that file too. The test removes it on
    # teardown only if the test created it (an existing operator-authored
    # .env is left alone).
    real_env = REPO_ROOT / "infra" / ".env"
    created_real_env = False
    if not real_env.exists():
        real_env.write_text("# created by test_compose_config.py — safe to delete\n")
        created_real_env = True
    env = tmp_path_factory.mktemp("env") / ".env"
    env.write_text(
        "\n".join(
            [
                "MEMEX_VAULT_PATH=/tmp/memex/vault",
                "MEMEX_DATA_PATH=/tmp/memex/data",
                "MEMEX_SYNCTHING_CONFIG=/tmp/memex/syncthing",
                "MEMEX_UID=1000",
                "MEMEX_GID=1000",
                "TZ=UTC",
                "MEMEX_CAPTURE_TOKEN_telegram=test_capture_token_0123456789abcdef",
                "MEMEX_CAPTURE_MAX_UPLOAD_MB=25",
                "MEMEX_WORKER_POLL_SECONDS=5",
                "MEMEX_WORKER_BATCH_PAUSE_SECONDS=60",
                "MEMEX_WORKER_BATCH_MAX=10",
                "MEMEX_WORKER_MAX_ATTEMPTS=5",
                "MEMEX_WORKER_CLAUDE_TIMEOUT_SECONDS=180",
                "MEMEX_WHISPER_MODEL_FILE=ggml-base.en.bin",
                "MEMEX_TELEGRAM_BOT_TOKEN=12345:abcdefghijklmnopqrstuvwxyzABCDEFGHIJ",
                "MEMEX_TELEGRAM_ALLOWED_CHAT_IDS=42",
                "MEMEX_TELEGRAM_CLAUDE_TIMEOUT_SECONDS=120",
                "MEMEX_TELEGRAM_MAX_DOWNLOAD_MB=25",
                "MEMEX_LOG_LEVEL=INFO",
                "",
            ]
        )
    )
    yield env
    if created_real_env:
        real_env.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def parsed(synthetic_env) -> dict:
    out = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "--env-file",
            str(synthetic_env),
            "config",
            "--format",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.stdout)


def test_compose_config_succeeds(parsed: dict):
    # If we got here, `docker compose config` exited 0.
    assert parsed["name"] == "memex"


def test_expected_services(parsed: dict):
    assert set(parsed["services"]) == {
        "capture_api",
        "worker",
        "telegram_bot",
        "syncthing",
        "dashboard",
    }


@pytest.mark.parametrize(
    "service",
    ["capture_api", "worker", "telegram_bot", "syncthing", "dashboard"],
)
def test_platform_arm64(parsed: dict, service: str):
    assert parsed["services"][service].get("platform") == "linux/arm64"


@pytest.mark.parametrize(
    "service",
    ["capture_api", "worker", "telegram_bot", "syncthing", "dashboard"],
)
def test_restart_policy(parsed: dict, service: str):
    assert parsed["services"][service].get("restart") == "unless-stopped"


@pytest.mark.parametrize(
    "service",
    ["capture_api", "worker", "telegram_bot", "syncthing", "dashboard"],
)
def test_logging_driver_with_rotation(parsed: dict, service: str):
    logging = parsed["services"][service].get("logging", {})
    assert logging.get("driver") == "json-file"
    options = logging.get("options", {})
    assert options.get("max-size") == "10m"
    assert options.get("max-file") in {"3", 3}


@pytest.mark.parametrize(
    "service,limit_bytes",
    [
        ("capture_api", 256 * 1024 * 1024),
        ("worker", 1024 * 1024 * 1024),
        ("telegram_bot", 384 * 1024 * 1024),
        ("syncthing", 256 * 1024 * 1024),
        ("dashboard", 384 * 1024 * 1024),
    ],
)
def test_memory_limits(parsed: dict, service: str, limit_bytes: int):
    # docker compose config emits mem_limit as bytes (int or string).
    raw = parsed["services"][service].get("mem_limit") or parsed["services"][
        service
    ].get("memswap_limit")
    assert raw is not None, f"{service} has no mem_limit"
    if isinstance(raw, str):
        raw_int = int(raw)
    else:
        raw_int = int(raw)
    assert raw_int == limit_bytes


def test_total_memory_budget_under_3gb(parsed: dict):
    total = sum(
        int(parsed["services"][s]["mem_limit"])
        for s in ["capture_api", "worker", "telegram_bot", "syncthing", "dashboard"]
    )
    # Budget ceiling per the compose-file comment block.
    assert total < 3 * 1024 * 1024 * 1024


def test_capture_api_has_http_healthcheck(parsed: dict):
    hc = parsed["services"]["capture_api"].get("healthcheck", {})
    test = hc.get("test") or []
    assert any("/healthz" in str(part) for part in test), test


def test_worker_has_healthcheck(parsed: dict):
    hc = parsed["services"]["worker"].get("healthcheck", {})
    assert hc.get("test"), "worker is missing a healthcheck"


def test_telegram_bot_has_healthcheck(parsed: dict):
    hc = parsed["services"]["telegram_bot"].get("healthcheck", {})
    assert hc.get("test"), "telegram_bot is missing a healthcheck"


def test_worker_depends_on_capture_api_healthy(parsed: dict):
    deps = parsed["services"]["worker"].get("depends_on", {})
    assert deps.get("capture_api", {}).get("condition") == "service_healthy"


def test_telegram_bot_depends_on_capture_api_healthy(parsed: dict):
    deps = parsed["services"]["telegram_bot"].get("depends_on", {})
    assert deps.get("capture_api", {}).get("condition") == "service_healthy"


def _volume_mode(volumes: list, target: str) -> str | None:
    for v in volumes:
        if v.get("target") == target:
            ro = v.get("read_only")
            if ro is True:
                return "ro"
            if ro is False or ro is None:
                return "rw"
    return None


def test_vault_readonly_on_telegram_bot(parsed: dict):
    mode = _volume_mode(
        parsed["services"]["telegram_bot"].get("volumes", []), "/vault"
    )
    assert mode == "ro", f"vault must be ro on telegram_bot, got {mode}"


def test_data_readonly_on_telegram_bot(parsed: dict):
    mode = _volume_mode(
        parsed["services"]["telegram_bot"].get("volumes", []), "/srv/memex/data"
    )
    assert mode == "ro", f"data must be ro on telegram_bot, got {mode}"


def test_vault_writable_on_worker(parsed: dict):
    mode = _volume_mode(parsed["services"]["worker"].get("volumes", []), "/vault")
    assert mode == "rw"


def test_data_writable_on_worker_and_capture_api(parsed: dict):
    for svc in ("worker", "capture_api"):
        mode = _volume_mode(
            parsed["services"][svc].get("volumes", []), "/srv/memex/data"
        )
        assert mode == "rw", f"{svc} should mount data rw"


def test_claude_auth_volume_on_claude_callers(parsed: dict):
    """The shared CLI auth volume is mounted by exactly the services that
    shell out to ``claude -p``: worker, telegram_bot, and dashboard."""
    by_service: dict[str, bool] = {}
    for svc, body in parsed["services"].items():
        mounts = body.get("volumes", []) or []
        has = any(
            (m.get("source") in {"claude_auth", "memex_claude_auth"})
            and m.get("type") == "volume"
            for m in mounts
        )
        by_service[svc] = has
    assert by_service == {
        "capture_api": False,
        "worker": True,
        "telegram_bot": True,
        "syncthing": False,
        "dashboard": True,
    }


def test_dashboard_has_http_healthcheck(parsed: dict):
    hc = parsed["services"]["dashboard"].get("healthcheck", {})
    test = hc.get("test") or []
    assert any("/healthz" in str(part) for part in test), test


def test_dashboard_depends_on_capture_api_healthy(parsed: dict):
    deps = parsed["services"]["dashboard"].get("depends_on", {})
    assert deps.get("capture_api", {}).get("condition") == "service_healthy"


def test_dashboard_publishes_8002(parsed: dict):
    ports = parsed["services"]["dashboard"].get("ports", []) or []
    targets = [int(p.get("target", 0)) for p in ports]
    assert 8002 in targets, f"dashboard must publish 8002, found {targets}"


def test_vault_writable_on_dashboard(parsed: dict):
    """Triage actions move inbox files; vault must be rw."""
    mode = _volume_mode(
        parsed["services"]["dashboard"].get("volumes", []), "/vault"
    )
    assert mode == "rw", f"dashboard vault must be rw, got {mode}"


def test_data_writable_on_dashboard(parsed: dict):
    """Retry/cancel updates queue rows; retrieval appends to claude_calls."""
    mode = _volume_mode(
        parsed["services"]["dashboard"].get("volumes", []), "/srv/memex/data"
    )
    assert mode == "rw", f"dashboard data must be rw, got {mode}"


def test_capture_api_does_not_publish_ports(parsed: dict):
    ports = parsed["services"]["capture_api"].get("ports", []) or []
    assert ports == [], f"capture_api must not publish ports, found {ports}"


def test_syncthing_web_ui_bound_to_localhost(parsed: dict):
    ports = parsed["services"]["syncthing"].get("ports", []) or []
    web = [p for p in ports if int(p.get("target", 0)) == 8384]
    assert len(web) == 1
    host_ip = web[0].get("host_ip", "") or web[0].get("published", "")
    # docker compose config emits host_ip="127.0.0.1" for our binding.
    assert "127.0.0.1" in str(host_ip) or web[0].get("host_ip") == "127.0.0.1", web[0]
