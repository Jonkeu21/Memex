"""Environment-driven configuration for the Telegram bot."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    bot_token: str
    allowed_chat_ids: frozenset[int]
    capture_api_base_url: str
    capture_api_token: str
    vault_dir: Path
    db_path: Path
    claude_bin: str
    claude_timeout_seconds: float
    max_download_mb: int
    log_level: str

    @property
    def max_download_bytes(self) -> int:
        return self.max_download_mb * 1024 * 1024


def _require(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"missing required env var: {name}")
    return value


def _parse_chat_ids(raw: str) -> frozenset[int]:
    out: set[int] = set()
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            out.add(int(piece))
        except ValueError as exc:
            raise ConfigError(f"invalid chat id in MEMEX_TELEGRAM_ALLOWED_CHAT_IDS: {piece!r}") from exc
    if not out:
        raise ConfigError("MEMEX_TELEGRAM_ALLOWED_CHAT_IDS must contain at least one chat id")
    return frozenset(out)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = env if env is not None else os.environ
    bot_token = _require(env, "MEMEX_TELEGRAM_BOT_TOKEN")
    chat_ids = _parse_chat_ids(_require(env, "MEMEX_TELEGRAM_ALLOWED_CHAT_IDS"))
    capture_url = env.get("MEMEX_CAPTURE_API_BASE_URL", "http://capture_api:8001").rstrip("/")
    capture_token = _require(env, "MEMEX_CAPTURE_API_TOKEN")
    vault_dir = Path(env.get("MEMEX_TELEGRAM_VAULT_DIR", "/vault"))
    db_path = Path(env.get("MEMEX_TELEGRAM_DB_PATH", "/srv/memex/data/memex.db"))
    claude_bin = env.get("MEMEX_TELEGRAM_CLAUDE_BIN", "claude").strip() or "claude"
    timeout_raw = env.get("MEMEX_TELEGRAM_CLAUDE_TIMEOUT_SECONDS", "120")
    try:
        claude_timeout = float(timeout_raw)
    except ValueError as exc:
        raise ConfigError(f"MEMEX_TELEGRAM_CLAUDE_TIMEOUT_SECONDS must be numeric: {timeout_raw!r}") from exc
    if claude_timeout <= 0:
        raise ConfigError("MEMEX_TELEGRAM_CLAUDE_TIMEOUT_SECONDS must be > 0")
    max_mb_raw = env.get("MEMEX_TELEGRAM_MAX_DOWNLOAD_MB", "25")
    try:
        max_mb = int(max_mb_raw)
    except ValueError as exc:
        raise ConfigError(f"MEMEX_TELEGRAM_MAX_DOWNLOAD_MB must be int: {max_mb_raw!r}") from exc
    if max_mb <= 0:
        raise ConfigError("MEMEX_TELEGRAM_MAX_DOWNLOAD_MB must be > 0")
    log_level = env.get("MEMEX_LOG_LEVEL", "INFO").upper()
    return Settings(
        bot_token=bot_token,
        allowed_chat_ids=chat_ids,
        capture_api_base_url=capture_url,
        capture_api_token=capture_token,
        vault_dir=vault_dir,
        db_path=db_path,
        claude_bin=claude_bin,
        claude_timeout_seconds=claude_timeout,
        max_download_mb=max_mb,
        log_level=log_level,
    )
