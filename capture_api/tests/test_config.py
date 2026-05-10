from __future__ import annotations

import pytest

from app.config import ConfigError, load_settings


def test_no_token_raises() -> None:
    with pytest.raises(ConfigError):
        load_settings({})


def test_empty_label_raises() -> None:
    with pytest.raises(ConfigError):
        load_settings({"MEMEX_CAPTURE_TOKEN_": "x"})


def test_empty_value_raises() -> None:
    with pytest.raises(ConfigError):
        load_settings({"MEMEX_CAPTURE_TOKEN_dev": ""})


def test_invalid_max_upload_raises() -> None:
    with pytest.raises(ConfigError):
        load_settings({"MEMEX_CAPTURE_TOKEN_dev": "x", "CAPTURE_MAX_UPLOAD_MB": "nope"})


def test_zero_max_upload_raises() -> None:
    with pytest.raises(ConfigError):
        load_settings({"MEMEX_CAPTURE_TOKEN_dev": "x", "CAPTURE_MAX_UPLOAD_MB": "0"})


def test_invalid_port_raises() -> None:
    with pytest.raises(ConfigError):
        load_settings({"MEMEX_CAPTURE_TOKEN_dev": "x", "CAPTURE_BIND_PORT": "70000"})


def test_invalid_log_level_raises() -> None:
    with pytest.raises(ConfigError):
        load_settings({"MEMEX_CAPTURE_TOKEN_dev": "x", "LOG_LEVEL": "LOUD"})


def test_label_lowercased_and_token_label_correct() -> None:
    s = load_settings({"MEMEX_CAPTURE_TOKEN_TELEGRAM": "abc"})
    assert s.tokens == {"telegram": "abc"}


def test_defaults_applied() -> None:
    s = load_settings({"MEMEX_CAPTURE_TOKEN_dev": "x"})
    assert s.bind_port == 8001
    assert s.max_upload_mb == 25
    assert s.log_level == "INFO"
