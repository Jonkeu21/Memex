"""Integration tests for the worker main loop."""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from worker import claude_runner
from worker import main as worker_main
from worker.db import (
    ClaudeTelemetry,
    insert_queue_row,
)
from worker.handlers.exceptions import PermanentHandlerError, TransientHandlerError
from worker.main import (
    WorkerContext,
    _process_row,
    run_once,
)
from worker.rate_limit import RateLimiter


def _ctx(settings, conn) -> WorkerContext:
    return WorkerContext(
        settings=settings,
        conn=conn,
        rate_limiter=RateLimiter(window_seconds=settings.rate_limit_window_seconds,
                                 threshold_ms=settings.rate_limit_threshold_ms),
        sleep=lambda s: None,
        now=lambda: datetime.now(timezone.utc),
        shutdown=lambda: False,
    )


def _make_outcome(folder="resources/ml-papers", title="Note", summary="S.", tags=None, confidence=0.9):
    return claude_runner.ClaudeOutcome(
        folder=folder, title=title, summary=summary, tags=tags or [],
        confidence=confidence,
        telemetry=ClaudeTelemetry(session_id="sess", input_tokens=10, output_tokens=5, duration_ms=42),
        exit_code=0,
    )


def _patch_claude(monkeypatch, outcome):
    def fake_invoke(**kw):
        return outcome
    monkeypatch.setattr(claude_runner, "invoke", fake_invoke)


def _patch_text_extract_passthrough(monkeypatch):
    from worker.handlers import text as text_handler
    monkeypatch.setattr(text_handler, "extract",
                        lambda payload: (json.loads(payload).get("text", ""), {}, None))


def test_full_text_capture_routes_to_folder(monkeypatch, settings, tmp_db, tmp_vault):
    _patch_claude(monkeypatch, _make_outcome(confidence=0.9, tags=["paper", "Transformer"]))
    qid = insert_queue_row(tmp_db, source_type="text", source_payload=json.dumps({"text": "hello"}), submitter="api:t")
    ctx = _ctx(settings, tmp_db)
    summary = run_once(ctx)
    assert summary.filed == 1
    row = tmp_db.execute("SELECT * FROM queue WHERE id=?", (qid,)).fetchone()
    assert row["status"] == "filed"
    assert row["vault_path"].startswith("resources/ml-papers/")
    note_text = (tmp_vault / row["vault_path"]).read_text()
    assert "id: " + str(qid) in note_text
    assert "taxonomy_path: resources/ml-papers" in note_text
    assert "needs_review: false" in note_text
    assert "tags: [paper, transformer]" in note_text


def test_url_capture_uses_original_url(monkeypatch, settings, tmp_db, tmp_vault):
    from worker.handlers import url_article
    monkeypatch.setattr(url_article, "extract",
                        lambda payload: ("Body text.", {"url": json.loads(payload)["url"]}, None))
    _patch_claude(monkeypatch, _make_outcome(folder="resources/ml-papers", confidence=0.9))
    qid = insert_queue_row(tmp_db, source_type="url",
                            source_payload=json.dumps({"url": "https://e.com/p"}),
                            submitter="api:t")
    summary = run_once(_ctx(settings, tmp_db))
    assert summary.filed == 1
    row = tmp_db.execute("SELECT * FROM queue WHERE id=?", (qid,)).fetchone()
    note_text = (tmp_vault / row["vault_path"]).read_text()
    assert "original_url: https://e.com/p" in note_text


def test_review_band_routes_to_matched_folder(monkeypatch, settings, tmp_db, tmp_vault):
    _patch_claude(monkeypatch, _make_outcome(folder="resources/ml-papers", confidence=0.70))
    qid = insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"x"}', submitter="api:t")
    run_once(_ctx(settings, tmp_db))
    row = tmp_db.execute("SELECT * FROM queue WHERE id=?", (qid,)).fetchone()
    assert row["status"] == "needs_review"
    assert row["vault_path"].startswith("resources/ml-papers/")
    note = (tmp_vault / row["vault_path"]).read_text()
    assert "needs_review: true" in note


def test_low_confidence_routes_to_inbox(monkeypatch, settings, tmp_db, tmp_vault):
    _patch_claude(monkeypatch, _make_outcome(folder="resources/ml-papers", confidence=0.40))
    qid = insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"x"}', submitter="api:t")
    run_once(_ctx(settings, tmp_db))
    row = tmp_db.execute("SELECT * FROM queue WHERE id=?", (qid,)).fetchone()
    assert row["status"] == "needs_review"
    assert row["vault_path"].startswith("_inbox/")
    note = (tmp_vault / row["vault_path"]).read_text()
    assert "taxonomy_path: _inbox" in note


def test_claude_transient_returns_to_queued(monkeypatch, settings, tmp_db):
    def boom(**kw):
        raise claude_runner.ClaudeTransientError("nope")
    monkeypatch.setattr(claude_runner, "invoke", boom)
    qid = insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"x"}', submitter="api:t")
    run_once(_ctx(settings, tmp_db))
    row = tmp_db.execute("SELECT * FROM queue WHERE id=?", (qid,)).fetchone()
    assert row["status"] == "queued"
    assert row["attempts"] == 1
    assert "claude_transient" in row["last_error"]


def test_claude_terminal_failure_at_max_attempts(monkeypatch, settings, tmp_db):
    def boom(**kw):
        raise claude_runner.ClaudeTransientError("nope")
    monkeypatch.setattr(claude_runner, "invoke", boom)
    qid = insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"x"}', submitter="api:t")
    tmp_db.execute("UPDATE queue SET attempts=4 WHERE id=?", (qid,))
    run_once(_ctx(settings, tmp_db))
    row = tmp_db.execute("SELECT * FROM queue WHERE id=?", (qid,)).fetchone()
    assert row["status"] == "failed"
    assert row["attempts"] == 5
    calls = tmp_db.execute("SELECT * FROM claude_calls").fetchall()
    assert len(calls) == 1
    assert calls[0]["exit_code"] == 1


def test_claude_malformed_json_retries(monkeypatch, settings, tmp_db):
    def boom(**kw):
        raise claude_runner.ClaudeMalformedJSONError("bad json")
    monkeypatch.setattr(claude_runner, "invoke", boom)
    qid = insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"x"}', submitter="api:t")
    run_once(_ctx(settings, tmp_db))
    row = tmp_db.execute("SELECT * FROM queue WHERE id=?", (qid,)).fetchone()
    assert row["status"] == "queued"
    assert "claude_invalid_json" in row["last_error"]


def test_handler_permanent_writes_inbox_stub(monkeypatch, settings, tmp_db, tmp_vault):
    from worker.handlers import url_article
    monkeypatch.setattr(url_article, "extract",
                        lambda payload: (_ for _ in ()).throw(PermanentHandlerError("no transcript")))
    qid = insert_queue_row(tmp_db, source_type="url",
                            source_payload=json.dumps({"url": "https://youtu.be/x"}),
                            submitter="api:t")
    run_once(_ctx(settings, tmp_db))
    row = tmp_db.execute("SELECT * FROM queue WHERE id=?", (qid,)).fetchone()
    assert row["status"] == "needs_review"
    assert row["vault_path"].startswith("_inbox/")
    note = (tmp_vault / row["vault_path"]).read_text()
    assert "extraction_failed: true" in note


def test_handler_transient_retries(monkeypatch, settings, tmp_db):
    from worker.handlers import url_article
    monkeypatch.setattr(url_article, "extract",
                        lambda payload: (_ for _ in ()).throw(TransientHandlerError("flaky")))
    qid = insert_queue_row(tmp_db, source_type="url",
                            source_payload=json.dumps({"url": "https://e.com"}),
                            submitter="api:t")
    run_once(_ctx(settings, tmp_db))
    row = tmp_db.execute("SELECT * FROM queue WHERE id=?", (qid,)).fetchone()
    assert row["status"] == "queued"


def test_filename_collision_yields_dash_n(monkeypatch, settings, tmp_db, tmp_vault):
    _patch_claude(monkeypatch, _make_outcome(folder="resources/ml-papers", title="Same Title", confidence=0.9))
    q1 = insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"a"}', submitter="api:t",
                          created_at="2026-05-10T10:00:00.000000Z")
    q2 = insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"b"}', submitter="api:t",
                          created_at="2026-05-10T11:00:00.000000Z")
    q3 = insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"c"}', submitter="api:t",
                          created_at="2026-05-10T12:00:00.000000Z")
    run_once(_ctx(settings, tmp_db))
    rows = tmp_db.execute("SELECT id, vault_path FROM queue ORDER BY id").fetchall()
    paths = [r["vault_path"] for r in rows]
    assert paths == [
        "resources/ml-papers/2026-05-10--same-title.md",
        "resources/ml-papers/2026-05-10--same-title-2.md",
        "resources/ml-papers/2026-05-10--same-title-3.md",
    ]


def test_batch_orders_oldest_first(monkeypatch, settings, tmp_db):
    seen: list[int] = []

    def fake_invoke(**kw):
        # record which item is in process by examining queue
        rows = list(tmp_db.execute("SELECT id FROM queue WHERE status='processing'"))
        seen.append(rows[0]["id"] if rows else -1)
        return _make_outcome(folder="resources/ml-papers")

    monkeypatch.setattr(claude_runner, "invoke", fake_invoke)
    a = insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"a"}',
                          submitter="api:t", created_at="2026-05-10T08:00:00.000000Z")
    b = insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"b"}',
                          submitter="api:t", created_at="2026-05-10T07:00:00.000000Z")
    run_once(_ctx(settings, tmp_db))
    assert seen == [b, a]


def test_taxonomy_reloaded_between_batches(monkeypatch, settings, tmp_db, tmp_vault):
    _patch_claude(monkeypatch, _make_outcome(folder="resources/ml-papers", confidence=0.65))
    qid = insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"x"}', submitter="api:t")
    run_once(_ctx(settings, tmp_db))
    row = tmp_db.execute("SELECT vault_path FROM queue WHERE id=?", (qid,)).fetchone()
    assert row["vault_path"].startswith("resources/ml-papers/")

    # Now raise the review threshold and re-run with another row
    tx = tmp_vault / "_meta" / "taxonomy.yml"
    new_yaml = tx.read_text().replace("review_threshold: 0.60", "review_threshold: 0.70")
    tx.write_text(new_yaml)

    qid2 = insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"y"}', submitter="api:t")
    run_once(_ctx(settings, tmp_db))
    row2 = tmp_db.execute("SELECT vault_path FROM queue WHERE id=?", (qid2,)).fetchone()
    assert row2["vault_path"].startswith("_inbox/")


def test_unknown_folder_from_claude_falls_back_to_inbox(monkeypatch, settings, tmp_db, tmp_vault):
    _patch_claude(monkeypatch, _make_outcome(folder="ghosts/of/yore", confidence=0.9))
    qid = insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"x"}', submitter="api:t")
    run_once(_ctx(settings, tmp_db))
    row = tmp_db.execute("SELECT * FROM queue WHERE id=?", (qid,)).fetchone()
    # falls back to default_route=_inbox; threshold check against global -> filed at 0.9 >= 0.80
    assert row["vault_path"].startswith("_inbox/")


def test_records_claude_call_on_success(monkeypatch, settings, tmp_db):
    _patch_claude(monkeypatch, _make_outcome(confidence=0.9))
    insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"x"}', submitter="api:t")
    run_once(_ctx(settings, tmp_db))
    rows = tmp_db.execute("SELECT * FROM claude_calls").fetchall()
    assert len(rows) == 1
    assert rows[0]["service"] == "worker"
    assert rows[0]["purpose"] == "file"
    assert rows[0]["exit_code"] == 0
    assert rows[0]["input_tokens"] == 10


def test_item_processed_log_emitted(monkeypatch, settings, tmp_db, capsys):
    from worker import logging as wl
    wl.configure("INFO")
    _patch_claude(monkeypatch, _make_outcome(confidence=0.9))
    insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"x"}', submitter="api:t")
    run_once(_ctx(settings, tmp_db))
    out = capsys.readouterr().out
    events = [json.loads(line) for line in out.strip().splitlines() if line.strip()]
    item_processed = [e for e in events if e.get("event") == "item_processed"]
    assert len(item_processed) == 1
    ev = item_processed[0]
    assert "queue_item_id" in ev
    assert "vault_path" in ev
    assert "confidence" in ev
    assert "duration_ms" in ev


def test_taxonomy_load_failure_aborts_batch(monkeypatch, settings, tmp_db, tmp_vault):
    (tmp_vault / "_meta" / "taxonomy.yml").write_text("schema_version: 99\n")
    summary = run_once(_ctx(settings, tmp_db))
    assert summary.claimed == 0


def test_vault_write_failure_retries(monkeypatch, settings, tmp_db):
    _patch_claude(monkeypatch, _make_outcome(folder="resources/ml-papers", confidence=0.9))
    from worker import vault_writer
    def boom(**kw):
        raise OSError("disk full")
    monkeypatch.setattr(vault_writer, "write_note", boom)
    qid = insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"x"}', submitter="api:t")
    run_once(_ctx(settings, tmp_db))
    row = tmp_db.execute("SELECT * FROM queue WHERE id=?", (qid,)).fetchone()
    assert row["status"] == "queued"
    assert "vault_write_failed" in row["last_error"]


def test_atomic_write_partial_no_target(tmp_path):
    """Vault-writer crash seam: target never appears even if temp is written."""
    from worker.vault_writer import VaultWriteCrash, atomic_write
    target = tmp_path / "n.md"
    with pytest.raises(VaultWriteCrash):
        atomic_write(target, "x", crash_after_temp=True)
    assert not target.exists()


def test_run_main_loop_one_iteration(monkeypatch, settings, tmp_db, tmp_vault):
    """Drive main() through one iteration, then trigger shutdown."""
    from worker import main as wm
    _patch_claude(monkeypatch, _make_outcome(confidence=0.9))
    insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"x"}', submitter="api:t")

    monkeypatch.setattr(wm, "_build_context", lambda s: _ctx(settings, tmp_db))
    monkeypatch.setattr(wm, "load_settings", lambda: settings)
    monkeypatch.setattr(wm, "_install_signal_handlers", lambda: None)

    # After the first sleep, request shutdown
    call_count = {"n": 0}
    real_sleep = __import__("time").sleep
    def fake_sleep(s):
        call_count["n"] += 1
        wm._shutdown_requested = True
    monkeypatch.setattr("worker.main.time", __import__("time"))
    monkeypatch.setattr("time.sleep", fake_sleep)

    wm._shutdown_requested = False
    rc = wm.main()
    wm._shutdown_requested = False
    assert rc == 0


def test_unknown_source_type_writes_inbox_stub(monkeypatch, settings, tmp_db):
    # bypass the queue's CHECK constraint by patching dispatch directly
    from worker import main as wm
    qid = insert_queue_row(tmp_db, source_type="text", source_payload='{"text":"x"}', submitter="api:t")
    row = tmp_db.execute("SELECT * FROM queue WHERE id=?", (qid,)).fetchone()
    def fake_dispatch(*a, **kw):
        raise PermanentHandlerError("unknown")
    monkeypatch.setattr(wm, "_dispatch_handler", fake_dispatch)
    from worker import taxonomy as tax
    t = tax.load(settings.taxonomy_path, settings.vault_dir)
    template = (settings.prompts_dir / "file.md").read_text()
    status = _process_row(row, _ctx(settings, tmp_db), t, template)
    assert status == "needs_review"
