"""Config loader: env-var validation."""
from __future__ import annotations

from pathlib import Path

import pytest

from bot.config import ConfigError, load_settings


_BASE_ENV = {
    "MEMEX_TELEGRAM_BOT_TOKEN": "bot-x",
    "MEMEX_TELEGRAM_ALLOWED_CHAT_IDS": "1,2,3",
    "MEMEX_CAPTURE_API_TOKEN": "cap-y",
}


def test_load_settings_defaults():
    s = load_settings(_BASE_ENV)
    assert s.bot_token == "bot-x"
    assert s.allowed_chat_ids == frozenset({1, 2, 3})
    assert s.capture_api_base_url == "http://capture_api:8001"
    assert s.vault_dir == Path("/vault")
    assert s.db_path == Path("/srv/memex/data/memex.db")
    assert s.claude_bin == "claude"
    assert s.claude_timeout_seconds == 120.0
    assert s.max_download_mb == 25
    assert s.max_download_bytes == 25 * 1024 * 1024
    assert s.log_level == "INFO"


def test_load_settings_missing_token_errors():
    env = {**_BASE_ENV}
    env.pop("MEMEX_TELEGRAM_BOT_TOKEN")
    with pytest.raises(ConfigError):
        load_settings(env)


def test_load_settings_missing_chat_ids_errors():
    env = {**_BASE_ENV, "MEMEX_TELEGRAM_ALLOWED_CHAT_IDS": ""}
    with pytest.raises(ConfigError):
        load_settings(env)


def test_load_settings_invalid_chat_id():
    env = {**_BASE_ENV, "MEMEX_TELEGRAM_ALLOWED_CHAT_IDS": "1,foo,3"}
    with pytest.raises(ConfigError):
        load_settings(env)


def test_load_settings_invalid_timeout():
    env = {**_BASE_ENV, "MEMEX_TELEGRAM_CLAUDE_TIMEOUT_SECONDS": "nope"}
    with pytest.raises(ConfigError):
        load_settings(env)


def test_load_settings_zero_timeout_rejected():
    env = {**_BASE_ENV, "MEMEX_TELEGRAM_CLAUDE_TIMEOUT_SECONDS": "0"}
    with pytest.raises(ConfigError):
        load_settings(env)


def test_load_settings_invalid_max_download():
    env = {**_BASE_ENV, "MEMEX_TELEGRAM_MAX_DOWNLOAD_MB": "0"}
    with pytest.raises(ConfigError):
        load_settings(env)


def test_load_settings_strips_trailing_slash_on_base_url():
    env = {**_BASE_ENV, "MEMEX_CAPTURE_API_BASE_URL": "http://api.example.com/"}
    s = load_settings(env)
    assert s.capture_api_base_url == "http://api.example.com"
