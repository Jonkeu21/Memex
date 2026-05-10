"""Retrieval handler.

Composes the prompt from ``prompts/retrieve.md``, runs ``claude -p`` in a
worker thread, parses the JSON envelope, renders the answer / sources /
quotes messages per CLAUDE.md, and records a row in ``claude_calls``.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from .. import claude_runner
from ..claude_runner import (
    ClaudeMalformedJSONError,
    ClaudeRunnerError,
    ClaudeTimeoutError,
    ClaudeTransientError,
    RetrievalOutcome,
)
from ..config import Settings
from ..logging import hash_chat_id, log_event
from ..rendering import render_retrieval


_FAILURE_MESSAGE = "I couldn't get a clean answer this time. Try again in a moment."


def _strip_question_prefix(text: str) -> str:
    """Strip a leading ``?`` (CLAUDE.md /find override convenience)."""
    text = (text or "").strip()
    if text.startswith("?"):
        return text[1:].strip()
    return text


async def handle_retrieval(
    *,
    message: Any,
    question: str,
    settings: Settings,
    prompt_template: str,
    record_call: Callable[..., None] | None = None,
    runner: Callable[..., Any] | None = None,
) -> None:
    """Run a retrieval and render results back to ``message``.

    Args:
        message: Telegram message-like object exposing ``reply_text``.
        question: question text (already stripped of /find or leading ?).
        settings: bot config.
        prompt_template: contents of ``prompts/retrieve.md``.
        record_call: optional ``(ts, purpose, session_id, input_tokens, output_tokens, duration_ms, exit_code, timeout) -> None``
            callback for ``claude_calls`` telemetry. Decoupled so tests can assert.
        runner: optional subprocess runner injection (forwarded to ``claude_runner.invoke``).
    """
    chat_id = getattr(message.chat, "id", None) if hasattr(message, "chat") else None
    submitter_hash = hash_chat_id(chat_id if chat_id is not None else "unknown")
    question = _strip_question_prefix(question)

    if not question:
        await message.reply_text("What would you like me to look up?")
        return

    prompt = claude_runner.render_prompt(
        prompt_template,
        question=question,
        vault_dir=settings.vault_dir,
    )

    log_event(
        "retrieval_started",
        intent="retrieval",
        submitter_hash=submitter_hash,
        question_size_bytes=len(question.encode("utf-8")),
    )

    def _run() -> RetrievalOutcome:
        return claude_runner.invoke(
            claude_bin=settings.claude_bin,
            prompt=prompt,
            timeout_seconds=settings.claude_timeout_seconds,
            runner=runner,
        )

    timed_out = False
    try:
        outcome = await asyncio.to_thread(_run)
    except ClaudeTimeoutError as exc:
        timed_out = True
        log_event(
            "retrieval_timeout",
            level=logging.WARNING,
            intent="retrieval",
            submitter_hash=submitter_hash,
            error_message=str(exc),
        )
        if record_call:
            record_call(
                purpose="retrieve",
                session_id=None,
                input_tokens=None,
                output_tokens=None,
                duration_ms=int(settings.claude_timeout_seconds * 1000),
                exit_code=-1,
                timeout=True,
            )
        await message.reply_text(
            "Sorry — the lookup took too long and was cancelled. Try a more specific question."
        )
        return
    except ClaudeMalformedJSONError as exc:
        log_event(
            "retrieval_malformed_json",
            level=logging.ERROR,
            intent="retrieval",
            submitter_hash=submitter_hash,
            error_message=str(exc),
        )
        if record_call:
            record_call(
                purpose="retrieve",
                session_id=None,
                input_tokens=None,
                output_tokens=None,
                duration_ms=None,
                exit_code=-2,
                timeout=False,
            )
        await message.reply_text(_FAILURE_MESSAGE)
        return
    except ClaudeTransientError as exc:
        log_event(
            "retrieval_transient_error",
            level=logging.ERROR,
            intent="retrieval",
            submitter_hash=submitter_hash,
            error_message=str(exc),
        )
        if record_call:
            record_call(
                purpose="retrieve",
                session_id=None,
                input_tokens=None,
                output_tokens=None,
                duration_ms=None,
                exit_code=-3,
                timeout=False,
            )
        await message.reply_text(_FAILURE_MESSAGE)
        return
    except ClaudeRunnerError as exc:
        # Belt-and-braces: catch any subclass we forgot to handle explicitly.
        log_event(
            "retrieval_unknown_error",
            level=logging.ERROR,
            intent="retrieval",
            submitter_hash=submitter_hash,
            error_message=str(exc),
        )
        await message.reply_text(_FAILURE_MESSAGE)
        return

    if record_call:
        record_call(
            purpose="retrieve",
            session_id=outcome.session_id,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            duration_ms=outcome.duration_ms,
            exit_code=outcome.exit_code,
            timeout=False,
        )

    rendered = render_retrieval(outcome)
    log_event(
        "retrieval_completed",
        intent="retrieval",
        submitter_hash=submitter_hash,
        claude_session_id=outcome.session_id,
        duration_ms=outcome.duration_ms,
        confidence=outcome.confidence,
        sources_count=len(outcome.sources),
        chunks=len(rendered.messages),
    )
    for body in rendered.messages:
        await message.reply_text(body, parse_mode="Markdown")
    _ = timed_out  # consumed; flag exists for future telemetry expansion
