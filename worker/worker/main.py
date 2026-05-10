"""Worker entry point and main loop.

The loop is single-threaded synchronous Python — no asyncio. SQLite under WAL
plus subprocess calls don't benefit from a coroutine runtime here, and the
straight-line code makes the retry/recovery semantics easier to audit.
"""
from __future__ import annotations

import json
import logging
import signal
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from worker import claude_runner, taxonomy as taxonomy_mod, vault_writer
from worker.config import Settings, load_settings
from worker.db import (
    ClaudeTelemetry,
    apply_migrations,
    connect,
    get_attempts,
    mark_failed,
    mark_filed,
    mark_needs_review,
    record_claude_call,
    release_for_retry,
    utc_now_iso,
)
from worker.db import claim_batch as db_claim_batch
from worker.handlers import file as file_handler
from worker.handlers import text as text_handler
from worker.handlers import url_article, voice
from worker.handlers.exceptions import PermanentHandlerError, TransientHandlerError
from worker.logging import configure as configure_logging
from worker.logging import log_event
from worker.rate_limit import RateLimiter
from worker.recovery import reset_stuck_processing


@dataclass
class TickSummary:
    claimed: int
    filed: int
    needs_review: int
    failed: int
    retried: int

    def non_empty(self) -> bool:
        return self.claimed > 0


@dataclass
class WorkerContext:
    settings: Settings
    conn: sqlite3.Connection
    rate_limiter: RateLimiter
    sleep: Callable[[float], None]
    now: Callable[[], datetime]
    shutdown: Callable[[], bool]


def _parse_iso(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def _dispatch_handler(
    row: sqlite3.Row,
    settings: Settings,
    captured_at: datetime,
) -> tuple[str, dict[str, Any], str | None]:
    source_type = row["source_type"]
    payload = row["source_payload"]
    if source_type == "url":
        return url_article.extract(payload)
    if source_type == "text":
        return text_handler.extract(payload)
    if source_type == "file":
        return file_handler.extract(
            payload,
            vault_dir=settings.vault_dir,
            captured_at=captured_at,
        )
    if source_type == "voice":
        return voice.extract(
            payload,
            vault_dir=settings.vault_dir,
            captured_at=captured_at,
            whisper_bin=settings.whisper_bin,
            whisper_model=settings.whisper_model,
        )
    raise PermanentHandlerError(f"unknown source_type: {source_type!r}")


def _route(
    confidence: float,
    matched_folder: str,
    taxonomy: taxonomy_mod.Taxonomy,
) -> tuple[str, str, bool, str]:
    """Return (target_folder, status, needs_review_flag, taxonomy_path_value)."""
    autonomous, review = taxonomy.resolve_thresholds(matched_folder)
    if confidence >= autonomous:
        return matched_folder, "filed", False, matched_folder
    if confidence >= review:
        return matched_folder, "needs_review", True, matched_folder
    return taxonomy.default_route, "needs_review", True, taxonomy.default_route


def _process_row(
    row: sqlite3.Row,
    ctx: WorkerContext,
    taxonomy: taxonomy_mod.Taxonomy,
    prompt_template: str,
) -> str:
    """Process a single claimed row. Returns status: filed | needs_review | failed | retried."""
    settings = ctx.settings
    conn = ctx.conn
    queue_id = int(row["id"])
    captured_at = _parse_iso(row["created_at"])
    source_type = row["source_type"]

    try:
        extracted_text, source_metadata, attachment_rel = _dispatch_handler(row, settings, captured_at)
    except PermanentHandlerError as exc:
        return _write_inbox_stub(ctx, row, taxonomy, str(exc))
    except TransientHandlerError as exc:
        return _retry_or_fail(ctx, row, f"handler_transient: {exc}")
    except Exception as exc:  # pragma: no cover - safety net
        log_event("handler_unexpected", level=logging.ERROR, queue_item_id=queue_id, error=str(exc))
        return _retry_or_fail(ctx, row, f"handler_unexpected: {exc}")

    prompt = claude_runner.render_prompt(
        prompt_template,
        taxonomy_yaml=taxonomy.raw_yaml,
        source_type=source_type,
        source_metadata=source_metadata,
        extracted_text=extracted_text,
    )

    call_ts = utc_now_iso()
    try:
        outcome = claude_runner.invoke(
            claude_bin=settings.claude_bin,
            prompt=prompt,
            timeout_seconds=settings.claude_timeout_seconds,
        )
    except claude_runner.ClaudeTransientError as exc:
        record_claude_call(
            conn,
            ts=call_ts, service="worker", purpose="file",
            queue_item_id=queue_id, session_id=None,
            input_tokens=None, output_tokens=None,
            duration_ms=None, exit_code=1,
        )
        log_event("claude_call_failed", level=logging.WARN, queue_item_id=queue_id, error=str(exc))
        return _retry_or_fail(ctx, row, f"claude_transient: {exc}")
    except claude_runner.ClaudeMalformedJSONError as exc:
        record_claude_call(
            conn,
            ts=call_ts, service="worker", purpose="file",
            queue_item_id=queue_id, session_id=None,
            input_tokens=None, output_tokens=None,
            duration_ms=None, exit_code=0,
        )
        log_event("claude_response_invalid_json", level=logging.WARN, queue_item_id=queue_id, error=str(exc))
        return _retry_or_fail(ctx, row, f"claude_invalid_json: {exc}")
    except claude_runner.ClaudeValidationError as exc:
        record_claude_call(
            conn,
            ts=call_ts, service="worker", purpose="file",
            queue_item_id=queue_id, session_id=None,
            input_tokens=None, output_tokens=None,
            duration_ms=None, exit_code=0,
        )
        log_event("claude_response_validation_failed", level=logging.WARN, queue_item_id=queue_id, error=str(exc))
        return _retry_or_fail(ctx, row, f"claude_validation: {exc}")

    record_claude_call(
        conn,
        ts=call_ts,
        service="worker",
        purpose="file",
        queue_item_id=queue_id,
        session_id=outcome.telemetry.session_id,
        input_tokens=outcome.telemetry.input_tokens,
        output_tokens=outcome.telemetry.output_tokens,
        duration_ms=outcome.telemetry.duration_ms,
        exit_code=outcome.exit_code,
    )
    if outcome.telemetry.duration_ms is not None:
        ctx.rate_limiter.record(outcome.telemetry.duration_ms)

    matched = outcome.folder
    if taxonomy.find_folder(matched) is None and matched != taxonomy.default_route:
        log_event(
            "claude_folder_unknown",
            level=logging.WARN,
            queue_item_id=queue_id,
            folder=matched,
        )
        matched = taxonomy.default_route

    target_folder, status, needs_review_flag, taxonomy_path_value = _route(
        outcome.confidence, matched, taxonomy
    )

    processed_at = utc_now_iso()
    payload = json.loads(row["source_payload"]) if row["source_payload"] else {}
    original_url = payload.get("url") if source_type == "url" else None
    front_matter = vault_writer.build_front_matter(
        queue_id=queue_id,
        source=source_type,
        captured_at=row["created_at"],
        processed_at=processed_at,
        confidence=outcome.confidence,
        taxonomy_path=taxonomy_path_value,
        tags=outcome.tags,
        needs_review=needs_review_flag,
        original_url=original_url,
        attachment=attachment_rel,
    )

    body_content = extracted_text
    title = outcome.title
    try:
        vault_path = vault_writer.write_note(
            vault_dir=settings.vault_dir,
            target_folder=target_folder,
            captured_date=captured_at.date(),
            title=title,
            summary=outcome.summary,
            body_content=body_content,
            front_matter=front_matter,
        )
    except Exception as exc:
        log_event("vault_write_failed", level=logging.ERROR, queue_item_id=queue_id, error=str(exc))
        return _retry_or_fail(ctx, row, f"vault_write_failed: {exc}")

    if status == "filed":
        mark_filed(conn, queue_id, vault_path, outcome.confidence, outcome.telemetry)
    else:
        mark_needs_review(conn, queue_id, vault_path, outcome.confidence, outcome.telemetry)

    log_event(
        "item_processed",
        queue_item_id=queue_id,
        status=status,
        vault_path=vault_path,
        confidence=outcome.confidence,
        duration_ms=outcome.telemetry.duration_ms,
        claude_session_id=outcome.telemetry.session_id,
    )
    return status


def _write_inbox_stub(
    ctx: WorkerContext,
    row: sqlite3.Row,
    taxonomy: taxonomy_mod.Taxonomy,
    reason: str,
) -> str:
    """Permanent handler failure → inbox stub note, status=needs_review."""
    settings = ctx.settings
    queue_id = int(row["id"])
    captured_at = _parse_iso(row["created_at"])
    processed_at = utc_now_iso()
    source_type = row["source_type"]
    payload = json.loads(row["source_payload"]) if row["source_payload"] else {}
    original_url = payload.get("url") if source_type == "url" else None

    title = f"Inbox: {source_type} extraction failed (#{queue_id})"
    summary = f"Extraction failed: {reason}"
    body = (
        f"Extraction failed for queue item {queue_id}.\n\n"
        f"Reason: {reason}\n\n"
        f"Source payload: {json.dumps(payload, indent=2, sort_keys=True)}\n"
    )

    front_matter = vault_writer.build_front_matter(
        queue_id=queue_id,
        source=source_type,
        captured_at=row["created_at"],
        processed_at=processed_at,
        confidence=0.0,
        taxonomy_path=taxonomy.default_route,
        tags=["extraction-failed"],
        needs_review=True,
        original_url=original_url,
        attachment=None,
    )
    rendered_fm = front_matter.render()
    rendered_fm = rendered_fm.replace(
        "needs_review: true\n", "needs_review: true\nextraction_failed: true\n"
    )
    note_body = (
        rendered_fm
        + f"\n# {title}\n\n{summary}\n\n## Source\n\n{body}"
    )

    folder = settings.vault_dir / taxonomy.default_route
    folder.mkdir(parents=True, exist_ok=True)
    slug = vault_writer.slugify(title)
    file_path = vault_writer.build_filename(folder, captured_at.date(), slug)
    vault_writer.atomic_write(file_path, note_body)
    vault_path = vault_writer.vault_relative(settings.vault_dir, file_path)

    mark_needs_review(
        ctx.conn,
        queue_id,
        vault_path,
        0.0,
        ClaudeTelemetry(None, None, None, None),
        last_error=f"extraction_failed: {reason}",
    )
    log_event(
        "item_inbox_stub_written",
        queue_item_id=queue_id,
        vault_path=vault_path,
        reason=reason,
    )
    return "needs_review"


def _retry_or_fail(ctx: WorkerContext, row: sqlite3.Row, last_error: str) -> str:
    queue_id = int(row["id"])
    attempts = get_attempts(ctx.conn, queue_id)
    if attempts >= ctx.settings.max_attempts:
        mark_failed(ctx.conn, queue_id, last_error)
        log_event(
            "item_failed_terminal",
            level=logging.ERROR,
            queue_item_id=queue_id,
            attempts=attempts,
            error=last_error,
        )
        return "failed"
    release_for_retry(ctx.conn, queue_id, last_error)
    log_event(
        "item_retry_scheduled",
        level=logging.WARN,
        queue_item_id=queue_id,
        attempts=attempts,
        error=last_error,
    )
    return "retried"


def run_once(ctx: WorkerContext) -> TickSummary:
    settings = ctx.settings
    try:
        taxonomy = taxonomy_mod.load(settings.taxonomy_path, settings.vault_dir)
    except taxonomy_mod.TaxonomyError as exc:
        log_event("taxonomy_load_failed", level=logging.ERROR, error=str(exc))
        return TickSummary(0, 0, 0, 0, 0)

    try:
        prompt_template = claude_runner.load_prompt_template(settings.prompts_dir)
    except OSError as exc:
        log_event("prompt_load_failed", level=logging.ERROR, error=str(exc))
        return TickSummary(0, 0, 0, 0, 0)

    rows = db_claim_batch(ctx.conn, settings.batch_max)
    summary = TickSummary(claimed=len(rows), filed=0, needs_review=0, failed=0, retried=0)
    for row in rows:
        if ctx.shutdown():
            break
        status = _process_row(row, ctx, taxonomy, prompt_template)
        if status == "filed":
            summary.filed += 1
        elif status == "needs_review":
            summary.needs_review += 1
        elif status == "failed":
            summary.failed += 1
        elif status == "retried":
            summary.retried += 1
    return summary


def _touch_health(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
    except OSError:
        pass


def _build_context(settings: Settings) -> WorkerContext:
    conn = connect(settings.db_path)
    apply_migrations(conn, settings.migrations_dir)
    rate_limiter = RateLimiter(
        window_seconds=settings.rate_limit_window_seconds,
        threshold_ms=settings.rate_limit_threshold_ms,
    )
    return WorkerContext(
        settings=settings,
        conn=conn,
        rate_limiter=rate_limiter,
        sleep=time.sleep,
        now=lambda: datetime.now(timezone.utc),
        shutdown=lambda: False,
    )


_shutdown_requested = False


def _install_signal_handlers() -> None:
    def handler(signum: int, _frame: Any) -> None:
        global _shutdown_requested
        _shutdown_requested = True
        log_event("shutdown_signal_received", signal=signum)

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    configure_logging(settings.log_level)
    _install_signal_handlers()

    ctx = _build_context(settings)
    ctx.shutdown = lambda: _shutdown_requested  # type: ignore[assignment]

    reset = reset_stuck_processing(ctx.conn)
    log_event("worker_started", reset_processing=reset)

    while not _shutdown_requested:
        tick_started = time.monotonic()
        log_event("batch_started")
        summary = run_once(ctx)
        duration_ms = int((time.monotonic() - tick_started) * 1000)
        log_event(
            "batch_completed",
            duration_ms=duration_ms,
            claimed=summary.claimed,
            filed=summary.filed,
            needs_review=summary.needs_review,
            failed=summary.failed,
            retried=summary.retried,
        )
        _touch_health(settings.healthcheck_path)

        if _shutdown_requested:
            break

        if summary.non_empty():
            time.sleep(settings.batch_pause_seconds)
            extra = ctx.rate_limiter.extra_pause_seconds()
            if extra > 0:
                log_event("rate_limit_pause", extra_seconds=extra)
                time.sleep(extra)
        else:
            time.sleep(settings.poll_seconds)

    log_event("worker_stopped")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
