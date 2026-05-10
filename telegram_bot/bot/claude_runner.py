"""Subprocess wrapper for ``claude -p`` for retrieval queries.

The wrapper renders the retrieval prompt template with the question and the
vault directory path, shells out to ``claude -p --output-format json``, parses
the envelope and the inner retrieval JSON, and returns a typed outcome plus
telemetry. Subprocess execution is synchronous; callers should run this
inside ``asyncio.to_thread`` so it does not block the event loop.

Three failure classes drive the renderer's error handling:

- ``ClaudeTimeoutError``  — subprocess timed out; tell the user politely.
- ``ClaudeTransientError`` — non-zero exit, missing binary, transport error.
- ``ClaudeMalformedJSONError`` — stdout was not parseable as the expected envelope.
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# Mirrors CLAUDE.md "Retrieval response schema".
QUOTE_MAX_CHARS = 280


class ClaudeRunnerError(Exception):
    """Base class for retrieval-side claude_runner failures."""


class ClaudeTimeoutError(ClaudeRunnerError):
    """Subprocess exceeded the configured timeout."""


class ClaudeTransientError(ClaudeRunnerError):
    """Non-zero exit, missing binary, or other transport-style failure."""


class ClaudeMalformedJSONError(ClaudeRunnerError):
    """stdout could not be parsed as the expected envelope."""


@dataclass
class RetrievalSource:
    path: str
    title: str


@dataclass
class RetrievalQuote:
    source_index: int
    text: str


@dataclass
class RetrievalOutcome:
    answer: str
    sources: list[RetrievalSource]
    quotes: list[RetrievalQuote]
    confidence: float
    session_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int
    exit_code: int
    raw_envelope: dict[str, Any] = field(default_factory=dict)


def render_prompt(template: str, *, question: str, vault_dir: Path) -> str:
    return (
        template
        .replace("{question}", question)
        .replace("{vault_dir}", str(vault_dir))
    )


def load_prompt_template(prompts_dir: Path) -> str:
    return (prompts_dir / "retrieve.md").read_text(encoding="utf-8")


def _truncate_quote(text: str) -> str:
    if len(text) <= QUOTE_MAX_CHARS:
        return text
    return text[: QUOTE_MAX_CHARS - 1].rstrip() + "…"


def _parse_envelope(stdout: str) -> tuple[dict[str, Any], dict[str, Any]]:
    stdout = stdout.strip()
    if not stdout:
        raise ClaudeMalformedJSONError("empty stdout from claude -p")
    try:
        outer = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ClaudeMalformedJSONError(f"outer parse failed: {exc}") from exc
    if isinstance(outer, dict) and "result" in outer:
        result = outer.get("result")
        if isinstance(result, str):
            try:
                inner = json.loads(result)
            except json.JSONDecodeError as exc:
                raise ClaudeMalformedJSONError(f"inner parse failed: {exc}") from exc
            return inner, outer
        if isinstance(result, dict):
            return result, outer
        raise ClaudeMalformedJSONError("envelope.result has unexpected type")
    if isinstance(outer, dict):
        return outer, {}
    raise ClaudeMalformedJSONError("envelope is not a JSON object")


def _validate_inner(inner: Any) -> tuple[str, list[RetrievalSource], list[RetrievalQuote], float]:
    if not isinstance(inner, dict):
        raise ClaudeMalformedJSONError("inner payload must be a JSON object")
    answer = inner.get("answer")
    sources_raw = inner.get("sources")
    quotes_raw = inner.get("quotes")
    confidence = inner.get("confidence")
    if not isinstance(answer, str):
        raise ClaudeMalformedJSONError("'answer' must be a string")
    if not isinstance(sources_raw, list):
        raise ClaudeMalformedJSONError("'sources' must be a list")
    if not isinstance(quotes_raw, list):
        raise ClaudeMalformedJSONError("'quotes' must be a list")
    if not isinstance(confidence, (int, float)):
        raise ClaudeMalformedJSONError("'confidence' must be numeric")
    confidence_f = float(confidence)
    if not (0.0 <= confidence_f <= 1.0):
        raise ClaudeMalformedJSONError(f"'confidence' out of range: {confidence_f}")

    sources: list[RetrievalSource] = []
    for i, item in enumerate(sources_raw):
        if not isinstance(item, dict):
            raise ClaudeMalformedJSONError(f"sources[{i}] must be a JSON object")
        path = item.get("path")
        title = item.get("title")
        if not isinstance(path, str) or not path.strip():
            raise ClaudeMalformedJSONError(f"sources[{i}].path must be a non-empty string")
        if path.startswith("/"):
            raise ClaudeMalformedJSONError(f"sources[{i}].path must be vault-relative (no leading slash)")
        if not isinstance(title, str):
            raise ClaudeMalformedJSONError(f"sources[{i}].title must be a string")
        sources.append(RetrievalSource(path=path.strip(), title=title))

    quotes: list[RetrievalQuote] = []
    for i, item in enumerate(quotes_raw):
        if not isinstance(item, dict):
            raise ClaudeMalformedJSONError(f"quotes[{i}] must be a JSON object")
        idx = item.get("source_index")
        text = item.get("text")
        if not isinstance(idx, int) or isinstance(idx, bool):
            raise ClaudeMalformedJSONError(f"quotes[{i}].source_index must be an int")
        if idx < 0 or (sources and idx >= len(sources)):
            raise ClaudeMalformedJSONError(f"quotes[{i}].source_index out of range: {idx}")
        if not isinstance(text, str):
            raise ClaudeMalformedJSONError(f"quotes[{i}].text must be a string")
        quotes.append(RetrievalQuote(source_index=idx, text=_truncate_quote(text)))

    return answer, sources, quotes, confidence_f


def invoke(
    *,
    claude_bin: str,
    prompt: str,
    timeout_seconds: float,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> RetrievalOutcome:
    """Run ``claude -p`` and return the parsed retrieval outcome.

    ``runner`` is an injection point for tests; if None, ``subprocess.run`` is
    used. The runner must accept ``(args, input, timeout, capture_output, text)``
    keyword arguments and return a CompletedProcess-like object with ``stdout``,
    ``stderr``, and ``returncode``.
    """
    runner = runner or subprocess.run
    args = [claude_bin, "-p", "--output-format", "json"]
    started = time.monotonic()
    try:
        result = runner(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise ClaudeTimeoutError(f"claude -p timed out after {timeout_seconds}s") from exc
    except FileNotFoundError as exc:
        raise ClaudeTransientError(f"claude binary not found: {claude_bin}") from exc

    duration_ms = int((time.monotonic() - started) * 1000)
    exit_code = int(result.returncode)
    if exit_code != 0:
        raise ClaudeTransientError(
            f"claude -p exited {exit_code}: {(result.stderr or '')[:500]}"
        )

    inner, envelope = _parse_envelope(result.stdout)
    answer, sources, quotes, confidence = _validate_inner(inner)

    session_id = None
    input_tokens = None
    output_tokens = None
    if envelope:
        session_id = envelope.get("session_id")
        input_tokens = envelope.get("input_tokens")
        output_tokens = envelope.get("output_tokens")
        if "usage" in envelope and isinstance(envelope["usage"], dict):
            input_tokens = input_tokens or envelope["usage"].get("input_tokens")
            output_tokens = output_tokens or envelope["usage"].get("output_tokens")

    return RetrievalOutcome(
        answer=answer,
        sources=sources,
        quotes=quotes,
        confidence=confidence,
        session_id=session_id if isinstance(session_id, str) else None,
        input_tokens=int(input_tokens) if isinstance(input_tokens, (int, float)) else None,
        output_tokens=int(output_tokens) if isinstance(output_tokens, (int, float)) else None,
        duration_ms=duration_ms,
        exit_code=exit_code,
        raw_envelope=envelope,
    )
