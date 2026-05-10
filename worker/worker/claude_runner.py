"""Subprocess wrapper for ``claude -p``.

The wrapper builds a filing prompt from ``prompts/file.md``, shells out, and
parses the JSON envelope. Distinct exception classes let the main loop pick
the right retry policy.
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worker.db import ClaudeTelemetry


class ClaudeRunnerError(Exception):
    """Base class for claude_runner failures."""


class ClaudeTransientError(ClaudeRunnerError):
    """Subprocess timeout or non-zero exit; retry."""


class ClaudeMalformedJSONError(ClaudeRunnerError):
    """stdout could not be parsed as JSON; retry."""


class ClaudeValidationError(ClaudeRunnerError):
    """Inner JSON missing/invalid fields; retry."""


@dataclass
class ClaudeOutcome:
    folder: str
    title: str
    summary: str
    tags: list[str]
    confidence: float
    telemetry: ClaudeTelemetry
    exit_code: int


def _truncate(text: str, limit: int = 30_000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


def render_prompt(
    template: str,
    *,
    taxonomy_yaml: str,
    source_type: str,
    source_metadata: dict[str, Any],
    extracted_text: str,
) -> str:
    return (
        template
        .replace("{taxonomy_yaml}", taxonomy_yaml)
        .replace("{source_type}", source_type)
        .replace("{source_metadata}", json.dumps(source_metadata, sort_keys=True))
        .replace("{extracted_text}", _truncate(extracted_text))
    )


def _parse_envelope(stdout: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (inner_json, envelope) parsed from claude -p stdout.

    The CLI's ``--output-format json`` emits an envelope like::

        {"session_id": "...", "result": "<text>", "input_tokens": ..., "output_tokens": ...}

    where ``result`` is a JSON string the model produced. If the outer parse
    yields a dict containing ``result``, parse that string. Otherwise treat
    the whole stdout as the inner payload.
    """
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


def _validate_inner(inner: Any) -> tuple[str, str, str, list[str], float]:
    if not isinstance(inner, dict):
        raise ClaudeValidationError("inner payload must be a JSON object")
    folder = inner.get("folder")
    title = inner.get("title")
    summary = inner.get("summary")
    tags = inner.get("tags")
    confidence = inner.get("confidence")
    if not isinstance(folder, str) or not folder.strip():
        raise ClaudeValidationError("'folder' must be a non-empty string")
    if not isinstance(title, str) or not title.strip():
        raise ClaudeValidationError("'title' must be a non-empty string")
    if not isinstance(summary, str):
        raise ClaudeValidationError("'summary' must be a string")
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise ClaudeValidationError("'tags' must be a list of strings")
    if not isinstance(confidence, (int, float)):
        raise ClaudeValidationError("'confidence' must be numeric")
    confidence_f = float(confidence)
    if not (0.0 <= confidence_f <= 1.0):
        raise ClaudeValidationError(f"'confidence' out of range: {confidence_f}")
    return folder.strip(), title.strip(), summary, list(tags), confidence_f


def invoke(
    *,
    claude_bin: str,
    prompt: str,
    timeout_seconds: float,
    runner: Any = None,
) -> ClaudeOutcome:
    """Run claude -p and return a parsed outcome.

    ``runner`` is an injection point for tests; if None, ``subprocess.run`` is
    used. The runner must accept ``(args, input, timeout)`` and return an
    object with ``stdout: str``, ``stderr: str``, and ``returncode: int``.
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
        duration_ms = int((time.monotonic() - started) * 1000)
        telemetry = ClaudeTelemetry(None, None, None, duration_ms)
        raise ClaudeTransientError(f"claude -p timed out after {timeout_seconds}s") from exc
    except FileNotFoundError as exc:
        raise ClaudeTransientError(f"claude binary not found: {claude_bin}") from exc

    duration_ms = int((time.monotonic() - started) * 1000)
    exit_code = int(result.returncode)
    if exit_code != 0:
        raise ClaudeTransientError(
            f"claude -p exited {exit_code}: {(result.stderr or '')[:500]}"
        )

    inner, envelope = _parse_envelope(result.stdout)
    folder, title, summary, tags, confidence = _validate_inner(inner)

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

    telemetry = ClaudeTelemetry(
        session_id=session_id if isinstance(session_id, str) else None,
        input_tokens=int(input_tokens) if isinstance(input_tokens, (int, float)) else None,
        output_tokens=int(output_tokens) if isinstance(output_tokens, (int, float)) else None,
        duration_ms=duration_ms,
    )

    return ClaudeOutcome(
        folder=folder,
        title=title,
        summary=summary,
        tags=tags,
        confidence=confidence,
        telemetry=telemetry,
        exit_code=exit_code,
    )


def load_prompt_template(prompts_dir: Path) -> str:
    return (prompts_dir / "file.md").read_text(encoding="utf-8")
