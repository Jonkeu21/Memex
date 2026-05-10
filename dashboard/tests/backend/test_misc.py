"""Tests for the smaller supporting modules: app, config, logging, db, frontmatter."""
from __future__ import annotations

import json
import logging as stdlogging
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import logging as backend_logging
from backend.app import create_app
from backend.config import ConfigError, Settings, load_settings
from backend.db import connect, table_exists, utc_now_iso
from backend.frontmatter import parse_file, parse_text, patch_field


# ── Health ──────────────────────────────────────────────────────────────────

def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_ok(client: TestClient) -> None:
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["db"] == "ok"
    assert body["checks"]["vault"] == "ok"


def test_readyz_unready_when_vault_missing(settings: Settings) -> None:
    bad_vault = settings.vault_dir.parent / "does-not-exist"
    bad_settings = Settings(
        bearer_token=settings.bearer_token,
        vault_dir=bad_vault,
        db_path=settings.db_path,
        claude_bin=settings.claude_bin,
        claude_timeout_seconds=settings.claude_timeout_seconds,
        retrieval_prompt_path=settings.retrieval_prompt_path,
        frontend_dist_dir=None,
        log_level="ERROR",
        bind_host="127.0.0.1",
        bind_port=0,
    )
    app = create_app(bad_settings)
    with TestClient(app) as c:
        resp = c.get("/readyz")
        assert resp.status_code == 503
        assert resp.json()["status"] == "not_ready"
        assert "missing" in resp.json()["checks"]["vault"]


# ── Config ──────────────────────────────────────────────────────────────────

def test_load_settings_requires_token() -> None:
    with pytest.raises(ConfigError, match="MEMEX_DASHBOARD_BEARER_TOKEN"):
        load_settings(env={})


def test_load_settings_defaults() -> None:
    s = load_settings(env={"MEMEX_DASHBOARD_BEARER_TOKEN": "x" * 32})
    assert s.bearer_token == "x" * 32
    assert s.vault_dir == Path("/vault")
    assert s.db_path == Path("/srv/memex/data/memex.db")
    assert s.claude_bin == "/usr/local/bin/claude"


def test_load_settings_rejects_bad_port() -> None:
    with pytest.raises(ConfigError):
        load_settings(env={
            "MEMEX_DASHBOARD_BEARER_TOKEN": "x",
            "MEMEX_DASHBOARD_BIND_PORT": "999999",
        })


def test_load_settings_rejects_bad_int() -> None:
    with pytest.raises(ConfigError):
        load_settings(env={
            "MEMEX_DASHBOARD_BEARER_TOKEN": "x",
            "MEMEX_DASHBOARD_BIND_PORT": "not-a-number",
        })


def test_load_settings_rejects_bad_float() -> None:
    with pytest.raises(ConfigError):
        load_settings(env={
            "MEMEX_DASHBOARD_BEARER_TOKEN": "x",
            "MEMEX_DASHBOARD_CLAUDE_TIMEOUT_SECONDS": "asdf",
        })


def test_load_settings_rejects_zero_timeout() -> None:
    with pytest.raises(ConfigError):
        load_settings(env={
            "MEMEX_DASHBOARD_BEARER_TOKEN": "x",
            "MEMEX_DASHBOARD_CLAUDE_TIMEOUT_SECONDS": "0",
        })


def test_load_settings_rejects_bad_log_level() -> None:
    with pytest.raises(ConfigError):
        load_settings(env={"MEMEX_DASHBOARD_BEARER_TOKEN": "x", "MEMEX_LOG_LEVEL": "TRACE"})


# ── DB ──────────────────────────────────────────────────────────────────────

def test_connect_creates_parent_dir(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "memex.db"
    conn = connect(nested)
    conn.close()
    assert nested.parent.is_dir()


def test_table_exists(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        assert table_exists(conn, "queue") is True
        assert table_exists(conn, "claude_calls") is True
        assert table_exists(conn, "definitely_not_a_table") is False
    finally:
        conn.close()


def test_utc_now_iso_format() -> None:
    s = utc_now_iso()
    assert s.endswith("Z")
    assert "T" in s


# ── Logging ─────────────────────────────────────────────────────────────────

def test_redact_redacts_secrets() -> None:
    payload = {
        "ok": "v",
        "token": "secret",
        "Authorization": "Bearer X",
        "api_key": "k",
        "nested": {"password": "pw"},
        # A non-secret-named list of secret-named dicts: the inner secrets are
        # redacted recursively.
        "items": [{"secret": "s"}],
    }
    out = backend_logging.redact(payload)
    assert out["token"] == "***"
    assert out["Authorization"] == "***"
    assert out["api_key"] == "***"
    assert out["nested"]["password"] == "***"
    assert out["items"][0]["secret"] == "***"
    assert out["ok"] == "v"


def test_redact_blanks_whole_value_when_key_matches() -> None:
    """A key whose name matches the secret regex is itself redacted entirely
    (the rule is "field with this key" → ``'***'``, not "search inside it")."""
    out = backend_logging.redact({"tokens_list": [{"secret": "s"}]})
    assert out["tokens_list"] == "***"


def test_redact_substitutes_body_size() -> None:
    out = backend_logging.redact({"text": "hello"})
    assert "text" not in out
    assert out["text_size_bytes"] == 5


def test_hash_chat_id_short_and_stable() -> None:
    h1 = backend_logging.hash_chat_id(123)
    h2 = backend_logging.hash_chat_id("123")
    assert len(h1) == 12
    assert h1 == h2


def _format_record_via_handler(level: int, msg: str, extras: dict, exc_info=None) -> str:
    """Run a one-shot record through ``JsonFormatter`` directly.

    ``capfd`` doesn't see the dashboard's StreamHandler because the handler
    captures ``sys.stdout`` at ``configure()`` time, so we exercise the
    formatter directly.
    """
    formatter = backend_logging.JsonFormatter()
    record = stdlogging.LogRecord(
        name="dashboard",
        level=level,
        pathname=__file__,
        lineno=0,
        msg=msg,
        args=None,
        exc_info=exc_info,
    )
    record.event = msg
    record.extras = extras
    return formatter.format(record)


def test_log_event_emits_json() -> None:
    line = _format_record_via_handler(stdlogging.INFO, "test_event", {"queue_item_id": 42})
    payload = json.loads(line)
    assert payload["event"] == "test_event"
    assert payload["service"] == "dashboard"
    assert payload["queue_item_id"] == 42


def test_json_formatter_with_exception() -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        import sys
        line = _format_record_via_handler(
            stdlogging.ERROR, "oops_event", {}, exc_info=sys.exc_info()
        )
    payload = json.loads(line)
    assert payload["error"]["type"] == "RuntimeError"
    assert payload["error"]["message"] == "boom"
    assert "traceback" in payload


def test_configure_is_idempotent() -> None:
    """Calling ``configure`` twice should not duplicate the handler."""
    backend_logging.configure("INFO")
    handler_count_before = len(stdlogging.getLogger().handlers)
    backend_logging.configure("DEBUG")
    handler_count_after = len(stdlogging.getLogger().handlers)
    assert handler_count_after == handler_count_before


# ── Front-matter ────────────────────────────────────────────────────────────

def test_parse_text_no_front_matter() -> None:
    parsed = parse_text("just a body, no fence")
    assert parsed.has_front_matter is False
    assert parsed.front_matter == {}
    assert parsed.body == "just a body, no fence"


def test_parse_text_basic() -> None:
    text = "---\nid: 1\ntitle: hello\n---\n\nbody text"
    parsed = parse_text(text)
    assert parsed.front_matter == {"id": 1, "title": "hello"}
    assert parsed.body.strip() == "body text"


def test_parse_text_invalid_yaml() -> None:
    text = "---\n[: bad\n---\nbody"
    parsed = parse_text(text)
    assert parsed.has_front_matter is False


def test_parse_text_no_closing_fence() -> None:
    parsed = parse_text("---\nid: 1\ntitle: hello\n")
    assert parsed.has_front_matter is False


def test_parse_file(tmp_path: Path) -> None:
    p = tmp_path / "x.md"
    p.write_text("---\nid: 7\n---\nbody\n", encoding="utf-8")
    parsed = parse_file(p)
    assert parsed.front_matter["id"] == 7


def test_patch_field_replaces_existing() -> None:
    text = "---\nid: 1\nneeds_review: true\n---\n\nbody"
    out = patch_field(text, "needs_review", False)
    assert "needs_review: false" in out
    assert "needs_review: true" not in out


def test_patch_field_appends_new() -> None:
    text = "---\nid: 1\n---\n\nbody"
    out = patch_field(text, "needs_review", False)
    assert "needs_review: false" in out


def test_patch_field_string_with_special_chars() -> None:
    text = "---\nid: 1\n---\n\nbody"
    out = patch_field(text, "taxonomy_path", "areas/health")
    assert "taxonomy_path: areas/health" in out


def test_patch_field_no_front_matter_raises() -> None:
    with pytest.raises(ValueError):
        patch_field("just a body", "x", "y")


# ── App / SPA serving ───────────────────────────────────────────────────────

def test_app_serves_spa_when_dist_present(tmp_path: Path, settings: Settings) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>SPA</html>", encoding="utf-8")
    (dist / "assets").mkdir()
    (dist / "assets" / "main.js").write_text("console.log('hi')", encoding="utf-8")
    new_settings = Settings(
        bearer_token=settings.bearer_token,
        vault_dir=settings.vault_dir,
        db_path=settings.db_path,
        claude_bin=settings.claude_bin,
        claude_timeout_seconds=settings.claude_timeout_seconds,
        retrieval_prompt_path=settings.retrieval_prompt_path,
        frontend_dist_dir=dist,
        log_level="ERROR",
        bind_host="127.0.0.1",
        bind_port=0,
    )
    app = create_app(new_settings)
    with TestClient(app) as c:
        # Root → index
        resp = c.get("/")
        assert resp.status_code == 200
        assert "SPA" in resp.text
        # Static asset
        resp2 = c.get("/assets/main.js")
        assert resp2.status_code == 200
        # Unknown SPA route → falls back to index
        resp3 = c.get("/queue")
        assert resp3.status_code == 200
        assert "SPA" in resp3.text


def test_app_404_when_no_frontend(client: TestClient) -> None:
    """When dist/ isn't built, root requests 404; APIs still work."""
    resp = client.get("/")
    assert resp.status_code == 404
    assert client.get("/api/v1/queue").status_code == 200
