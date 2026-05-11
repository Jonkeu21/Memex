"""Retrieval chat endpoint.

Shells out to ``claude -p`` with the retrieval prompt template + the user's
question, validates the structured JSON envelope per CLAUDE.md "Retrieval
response schema", and returns it unchanged. The frontend renders the result
as a single chat bubble with answer / source chips / quotes.

Each invocation also writes a row to ``claude_calls`` with ``service='dashboard'``,
``purpose='retrieve'`` so the rate-limit page surfaces dashboard-driven traffic.
"""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..auth import require_token
from ..claude_runner import (
    ClaudeMalformedJSONError,
    ClaudeNotAuthenticatedError,
    ClaudeRunnerError,
    ClaudeTimeoutError,
    ClaudeTransientError,
    invoke,
    load_prompt_template,
    render_prompt,
)
from ..logging import log_event
from ..schemas import (
    RetrievalQuote,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalSource,
)
from ..vault import VaultPathError, safe_join

router = APIRouter(prefix="/api/v1/retrieval", tags=["retrieval"])


def _record_call(
    conn: sqlite3.Connection,
    *,
    session_id: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    duration_ms: int | None,
    exit_code: int,
) -> None:
    """Insert a row into claude_calls if the table is present.

    Best-effort: if the worker hasn't applied its migration yet, this is a
    no-op. Telemetry must never crash a retrieval.
    """
    try:
        conn.execute(
            """
            INSERT INTO claude_calls
                (ts, service, purpose, queue_item_id, session_id,
                 input_tokens, output_tokens, duration_ms, exit_code)
            VALUES (?, 'dashboard', 'retrieve', NULL, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                session_id,
                input_tokens,
                output_tokens,
                duration_ms,
                exit_code,
            ),
        )
    except sqlite3.Error as exc:
        log_event(
            "claude_call_telemetry_skipped",
            level=20,
            error_type=type(exc).__name__,
            error_message=str(exc)[:200],
        )


@router.post(
    "",
    response_model=RetrievalResponse,
    dependencies=[Depends(require_token)],
)
async def retrieve(payload: RetrievalRequest, request: Request) -> RetrievalResponse:
    settings = request.app.state.settings
    conn: sqlite3.Connection = request.app.state.db

    try:
        template = load_prompt_template(settings.retrieval_prompt_path)
    except OSError as exc:
        log_event(
            "retrieval_prompt_unreadable",
            level=40,
            path=str(settings.retrieval_prompt_path),
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "prompt_unreadable",
                    "message": f"could not read retrieval prompt: {exc}",
                }
            },
        )

    prompt = render_prompt(
        template,
        question=payload.question,
        vault_dir=settings.vault_dir,
    )

    # ``app.py`` initialises ``claude_runner_invoke`` to ``None`` so tests can
    # set it without monkey-patching; ``getattr``'s third arg is the default
    # only when the attribute is *absent*, so we ``or invoke`` to fall back
    # when it is present but ``None``.
    runner = getattr(request.app.state, "claude_runner_invoke", None) or invoke

    def _invoke():
        return runner(
            claude_bin=settings.claude_bin,
            prompt=prompt,
            timeout_seconds=settings.claude_timeout_seconds,
            add_dirs=[str(settings.vault_dir)],
        )

    try:
        outcome = await asyncio.to_thread(_invoke)
    except ClaudeTimeoutError as exc:
        _record_call(conn, session_id=None, input_tokens=None, output_tokens=None,
                     duration_ms=int(settings.claude_timeout_seconds * 1000), exit_code=-1)
        log_event(
            "retrieval_timeout",
            level=30,
            timeout_seconds=settings.claude_timeout_seconds,
            error_message=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={
                "error": {
                    "code": "retrieval_timeout",
                    "message": (
                        f"claude -p exceeded {settings.claude_timeout_seconds:.0f}s. "
                        "Try a narrower question or check the worker isn't holding the session."
                    ),
                }
            },
        )
    except ClaudeNotAuthenticatedError as exc:
        _record_call(conn, session_id=None, input_tokens=None, output_tokens=None,
                     duration_ms=None, exit_code=-3)
        log_event("retrieval_unauthenticated", level=40, error_message=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "claude_not_authenticated",
                    "message": (
                        "Claude CLI not authenticated. Run `claude /login` inside "
                        "the claude_auth volume context (see docs/deployment.md)."
                    ),
                }
            },
        )
    except ClaudeMalformedJSONError as exc:
        _record_call(conn, session_id=None, input_tokens=None, output_tokens=None,
                     duration_ms=None, exit_code=-2)
        log_event("retrieval_malformed_json", level=40, error_message=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "malformed_response",
                    "message": (
                        "claude -p response did not match the retrieval JSON envelope: "
                        f"{exc}"
                    ),
                }
            },
        )
    except ClaudeTransientError as exc:
        _record_call(conn, session_id=None, input_tokens=None, output_tokens=None,
                     duration_ms=None, exit_code=-3)
        log_event("retrieval_transient_failure", level=40, error_message=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "code": "claude_transient",
                    "message": str(exc),
                }
            },
        )
    except ClaudeRunnerError as exc:
        _record_call(conn, session_id=None, input_tokens=None, output_tokens=None,
                     duration_ms=None, exit_code=-3)
        log_event("retrieval_runner_failure", level=40, error_message=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "claude_failed", "message": str(exc)}},
        )

    # Mark sources whose paths don't actually exist on disk so the frontend can
    # render a warning chip rather than a broken link.
    sources_out: list[RetrievalSource] = []
    for src in outcome.sources:
        exists = False
        try:
            absolute = safe_join(settings.vault_dir, src.path)
            exists = absolute.is_file()
        except VaultPathError:
            exists = False
        sources_out.append(RetrievalSource(path=src.path, title=src.title, exists=exists))

    quotes_out = [RetrievalQuote(source_index=q.source_index, text=q.text) for q in outcome.quotes]

    _record_call(
        conn,
        session_id=outcome.session_id,
        input_tokens=outcome.input_tokens,
        output_tokens=outcome.output_tokens,
        duration_ms=outcome.duration_ms,
        exit_code=outcome.exit_code,
    )
    log_event(
        "retrieval_completed",
        duration_ms=outcome.duration_ms,
        confidence=outcome.confidence,
        source_count=len(outcome.sources),
        quote_count=len(outcome.quotes),
        claude_session_id=outcome.session_id,
    )

    return RetrievalResponse(
        answer=outcome.answer,
        sources=sources_out,
        quotes=quotes_out,
        confidence=outcome.confidence,
        duration_ms=outcome.duration_ms,
        session_id=outcome.session_id,
    )
