"""Tests for worker.config."""
from __future__ import annotations

import pytest

from worker.config import ConfigError, load_settings


def test_defaults():
    s = load_settings({})
    assert s.poll_seconds == 5.0
    assert s.batch_max == 10
    assert s.batch_pause_seconds == 60.0
    assert s.max_attempts == 5
    assert s.claude_bin == "claude"
    assert str(s.db_path) == "/srv/memex/data/memex.db"
    assert s.log_level == "INFO"


def test_overrides():
    s = load_settings({
        "MEMEX_WORKER_POLL_SECONDS": "0.5",
        "MEMEX_WORKER_BATCH_MAX": "3",
        "MEMEX_WORKER_BATCH_PAUSE_SECONDS": "0.1",
        "MEMEX_WORKER_MAX_ATTEMPTS": "2",
        "MEMEX_WORKER_CLAUDE_BIN": "fake",
        "MEMEX_LOG_LEVEL": "debug",
    })
    assert s.poll_seconds == 0.5
    assert s.batch_max == 3
    assert s.batch_pause_seconds == 0.1
    assert s.max_attempts == 2
    assert s.claude_bin == "fake"
    assert s.log_level == "DEBUG"


def test_invalid_int_raises():
    with pytest.raises(ConfigError):
        load_settings({"MEMEX_WORKER_BATCH_MAX": "not-int"})


def test_min_val_int():
    with pytest.raises(ConfigError):
        load_settings({"MEMEX_WORKER_BATCH_MAX": "0"})


def test_invalid_float_raises():
    with pytest.raises(ConfigError):
        load_settings({"MEMEX_WORKER_POLL_SECONDS": "abc"})


def test_min_val_float():
    with pytest.raises(ConfigError):
        load_settings({"MEMEX_WORKER_POLL_SECONDS": "0.0"})


def test_log_level_invalid():
    with pytest.raises(ConfigError):
        load_settings({"MEMEX_LOG_LEVEL": "TRACE"})
