"""Environment-driven configuration for the capture API.

Loaded once at startup; if anything is missing or invalid the process exits
with a clear message.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(RuntimeError):
    pass


_TOKEN_PREFIX = "MEMEX_CAPTURE_TOKEN_"


@dataclass(frozen=True)
class Settings:
    tokens: dict[str, str]
    db_path: Path
    inbox_dir: Path
    max_upload_bytes: int
    bind_host: str
    bind_port: int
    log_level: str
    contract_version: str = "1"

    @property
    def max_upload_mb(self) -> int:
        return self.max_upload_bytes // (1024 * 1024)


def _read_tokens(env: dict[str, str]) -> dict[str, str]:
    tokens: dict[str, str] = {}
    for key, value in env.items():
        if not key.startswith(_TOKEN_PREFIX):
            continue
        label = key[len(_TOKEN_PREFIX):].lower()
        if not label:
            raise ConfigError(f"env var {key!r} has empty label suffix")
        if not value:
            raise ConfigError(f"env var {key!r} is empty")
        tokens[label] = value
    if not tokens:
        raise ConfigError(
            "no capture tokens configured: set at least one "
            "MEMEX_CAPTURE_TOKEN_<LABEL>=<value>"
        )
    return tokens


def load_settings(env: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ if env is None else env)

    try:
        max_upload_mb = int(env.get("CAPTURE_MAX_UPLOAD_MB", "25"))
    except ValueError as exc:
        raise ConfigError("CAPTURE_MAX_UPLOAD_MB must be an integer") from exc
    if max_upload_mb <= 0:
        raise ConfigError("CAPTURE_MAX_UPLOAD_MB must be > 0")

    try:
        bind_port = int(env.get("CAPTURE_BIND_PORT", "8001"))
    except ValueError as exc:
        raise ConfigError("CAPTURE_BIND_PORT must be an integer") from exc
    if not (0 < bind_port < 65536):
        raise ConfigError("CAPTURE_BIND_PORT must be in (0, 65535]")

    log_level = env.get("LOG_LEVEL", "INFO").upper()
    if log_level not in {"DEBUG", "INFO", "WARN", "WARNING", "ERROR"}:
        raise ConfigError(f"LOG_LEVEL invalid: {log_level!r}")

    return Settings(
        tokens=_read_tokens(env),
        db_path=Path(env.get("CAPTURE_DB_PATH", "/data/queue.db")),
        inbox_dir=Path(env.get("CAPTURE_INBOX_DIR", "/data/inbox")),
        max_upload_bytes=max_upload_mb * 1024 * 1024,
        bind_host=env.get("CAPTURE_BIND_HOST", "0.0.0.0"),
        bind_port=bind_port,
        log_level=log_level,
    )
