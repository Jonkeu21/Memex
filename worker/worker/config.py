"""Environment-driven configuration for the worker.

All env vars use the ``MEMEX_WORKER_`` prefix to match CLAUDE.md
(``MEMEX_WORKER_BATCH_PAUSE_SECONDS`` is the canonical example).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    db_path: Path
    vault_dir: Path
    inbox_dir: Path
    taxonomy_path: Path
    migrations_dir: Path
    prompts_dir: Path

    poll_seconds: float
    batch_max: int
    batch_pause_seconds: float
    max_attempts: int

    claude_bin: str
    claude_timeout_seconds: float

    whisper_bin: str
    whisper_model: Path

    rate_limit_window_seconds: float
    rate_limit_threshold_ms: int

    healthcheck_path: Path
    log_level: str


def _int(env: dict[str, str], key: str, default: int, *, min_val: int | None = None) -> int:
    raw = env.get(key, str(default))
    try:
        v = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc
    if min_val is not None and v < min_val:
        raise ConfigError(f"{key} must be >= {min_val}")
    return v


def _float(env: dict[str, str], key: str, default: float, *, min_val: float | None = None) -> float:
    raw = env.get(key, str(default))
    try:
        v = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}") from exc
    if min_val is not None and v < min_val:
        raise ConfigError(f"{key} must be >= {min_val}")
    return v


def load_settings(env: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ if env is None else env)

    log_level = env.get("MEMEX_LOG_LEVEL", "INFO").upper()
    if log_level not in {"DEBUG", "INFO", "WARN", "WARNING", "ERROR"}:
        raise ConfigError(f"MEMEX_LOG_LEVEL invalid: {log_level!r}")

    here = Path(__file__).resolve().parent.parent
    return Settings(
        db_path=Path(env.get("MEMEX_WORKER_DB_PATH", "/srv/memex/data/memex.db")),
        vault_dir=Path(env.get("MEMEX_WORKER_VAULT_DIR", "/srv/memex/vault")),
        inbox_dir=Path(env.get("MEMEX_WORKER_INBOX_DIR", "/srv/memex/data/uploads")),
        taxonomy_path=Path(env.get("MEMEX_WORKER_TAXONOMY_PATH", "/srv/memex/vault/_meta/taxonomy.yml")),
        migrations_dir=Path(env.get("MEMEX_WORKER_MIGRATIONS_DIR", str(here / "migrations"))),
        prompts_dir=Path(env.get("MEMEX_WORKER_PROMPTS_DIR", str(here / "prompts"))),
        poll_seconds=_float(env, "MEMEX_WORKER_POLL_SECONDS", 5.0, min_val=0.1),
        batch_max=_int(env, "MEMEX_WORKER_BATCH_MAX", 10, min_val=1),
        batch_pause_seconds=_float(env, "MEMEX_WORKER_BATCH_PAUSE_SECONDS", 60.0, min_val=0.0),
        max_attempts=_int(env, "MEMEX_WORKER_MAX_ATTEMPTS", 5, min_val=1),
        claude_bin=env.get("MEMEX_WORKER_CLAUDE_BIN", "claude"),
        claude_timeout_seconds=_float(env, "MEMEX_WORKER_CLAUDE_TIMEOUT_SECONDS", 180.0, min_val=1.0),
        whisper_bin=env.get("MEMEX_WORKER_WHISPER_BIN", "whisper-cpp"),
        whisper_model=Path(env.get("MEMEX_WORKER_WHISPER_MODEL", "/models/ggml-base.en.bin")),
        rate_limit_window_seconds=_float(env, "MEMEX_WORKER_RATE_LIMIT_WINDOW_SECONDS", 300.0, min_val=1.0),
        rate_limit_threshold_ms=_int(env, "MEMEX_WORKER_RATE_LIMIT_THRESHOLD_MS", 180_000, min_val=0),
        healthcheck_path=Path(env.get("MEMEX_WORKER_HEALTHCHECK_PATH", "/tmp/memex-worker.healthy")),
        log_level=log_level,
    )
