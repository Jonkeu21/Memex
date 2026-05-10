"""Environment-driven configuration for the dashboard backend.

Loaded once at startup; if anything is missing or invalid the process exits
with a clear message. Variable names follow the ``MEMEX_DASHBOARD_*`` prefix
convention established by capture_api / worker / telegram_bot.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    bearer_token: str
    vault_dir: Path
    db_path: Path
    claude_bin: str
    claude_timeout_seconds: float
    retrieval_prompt_path: Path
    frontend_dist_dir: Path | None
    log_level: str
    bind_host: str
    bind_port: int
    contract_version: str = "1"


def _read_int(env: dict[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc


def _read_float(env: dict[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}") from exc


def load_settings(env: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ if env is None else env)

    token = env.get("MEMEX_DASHBOARD_BEARER_TOKEN", "")
    if not token:
        raise ConfigError(
            "MEMEX_DASHBOARD_BEARER_TOKEN is required: shared bearer token "
            "for mutating endpoints"
        )

    vault_dir = Path(env.get("MEMEX_DASHBOARD_VAULT_DIR", "/vault"))
    db_path = Path(env.get("MEMEX_DASHBOARD_DB_PATH", "/srv/memex/data/memex.db"))
    claude_bin = env.get("MEMEX_DASHBOARD_CLAUDE_BIN", "/usr/local/bin/claude")
    claude_timeout = _read_float(env, "MEMEX_DASHBOARD_CLAUDE_TIMEOUT_SECONDS", 120.0)
    if claude_timeout <= 0:
        raise ConfigError("MEMEX_DASHBOARD_CLAUDE_TIMEOUT_SECONDS must be > 0")

    default_prompt = Path(__file__).parent / "prompts" / "retrieve.md"
    retrieval_prompt_path = Path(
        env.get("MEMEX_DASHBOARD_RETRIEVAL_PROMPT_PATH", str(default_prompt))
    )

    frontend_dist_raw = env.get("MEMEX_DASHBOARD_FRONTEND_DIST_DIR")
    if frontend_dist_raw:
        frontend_dist_dir: Path | None = Path(frontend_dist_raw)
    else:
        # Default: ../frontend/dist sibling of backend/
        candidate = Path(__file__).parent.parent / "frontend" / "dist"
        frontend_dist_dir = candidate if candidate.is_dir() else None

    log_level = env.get("MEMEX_LOG_LEVEL", "INFO").upper()
    if log_level not in {"DEBUG", "INFO", "WARN", "WARNING", "ERROR"}:
        raise ConfigError(f"MEMEX_LOG_LEVEL invalid: {log_level!r}")

    bind_host = env.get("MEMEX_DASHBOARD_BIND_HOST", "0.0.0.0")
    bind_port = _read_int(env, "MEMEX_DASHBOARD_BIND_PORT", 8002)
    if not (0 < bind_port < 65536):
        raise ConfigError("MEMEX_DASHBOARD_BIND_PORT must be in (0, 65535]")

    return Settings(
        bearer_token=token,
        vault_dir=vault_dir,
        db_path=db_path,
        claude_bin=claude_bin,
        claude_timeout_seconds=claude_timeout,
        retrieval_prompt_path=retrieval_prompt_path,
        frontend_dist_dir=frontend_dist_dir,
        log_level=log_level,
        bind_host=bind_host,
        bind_port=bind_port,
    )
