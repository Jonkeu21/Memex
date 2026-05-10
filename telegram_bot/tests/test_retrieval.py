"""Retrieval handler: happy path, malformed JSON, timeout, empty sources."""
from __future__ import annotations

import logging
import subprocess
from typing import Any

import pytest

from bot import claude_runner
from bot.handlers.retrieval import handle_retrieval
from tests.conftest import FakeMessage, make_envelope, make_runner


PROMPT_TEMPLATE = "vault={vault_dir}\nq={question}"

GOOD_INNER = {
    "answer": "**Yes** — based on your sleep notes, magnesium glycinate helped.",
    "sources": [
        {"path": "areas/health/2026-03-19--sleep.md", "title": "Sleep experiment"},
        {"path": "resources/ml-papers/2026-04-02--rope.md", "title": "RoPE notes"},
    ],
    "quotes": [
        {"source_index": 0, "text": "WASO dropped 18 minutes after starting magnesium."},
        {"source_index": 1, "text": "Position interpolation degrades smoothly past 4× context."},
    ],
    "confidence": 0.82,
}


@pytest.mark.asyncio
async def test_retrieval_happy_path_renders_three_messages(settings):
    msg = FakeMessage(text="how is my sleep?")
    runner = make_runner(stdout=make_envelope(GOOD_INNER))
    calls: list[dict[str, Any]] = []
    await handle_retrieval(
        message=msg,
        question="how is my sleep?",
        settings=settings,
        prompt_template=PROMPT_TEMPLATE,
        record_call=lambda **kw: calls.append(kw),
        runner=runner,
    )
    # 3 messages: answer, sources, quotes.
    assert len(msg.replies) == 3
    assert "Yes" in msg.replies[0].text
    assert msg.replies[0].parse_mode == "Markdown"
    assert "*Sources*" in msg.replies[1].text
    assert "areas/health/2026-03-19--sleep.md" in msg.replies[1].text
    assert "*Quotes*" in msg.replies[2].text
    assert msg.replies[2].text.count("> [") == 2
    assert calls and calls[0]["session_id"] == "sess-1"
    assert calls[0]["timeout"] is False


@pytest.mark.asyncio
async def test_retrieval_empty_sources_appends_marker(settings):
    inner = {"answer": "Nothing about that.", "sources": [], "quotes": [], "confidence": 0.1}
    msg = FakeMessage(text="who painted the moon?")
    runner = make_runner(stdout=make_envelope(inner))
    await handle_retrieval(
        message=msg,
        question="who painted the moon?",
        settings=settings,
        prompt_template=PROMPT_TEMPLATE,
        runner=runner,
    )
    assert len(msg.replies) == 1
    assert "_No sources found in vault._" in msg.replies[0].text


@pytest.mark.asyncio
async def test_retrieval_malformed_json(settings):
    msg = FakeMessage(text="what?")
    runner = make_runner(stdout="not json at all")
    calls: list[dict[str, Any]] = []
    await handle_retrieval(
        message=msg,
        question="what?",
        settings=settings,
        prompt_template=PROMPT_TEMPLATE,
        record_call=lambda **kw: calls.append(kw),
        runner=runner,
    )
    assert "couldn't get a clean answer" in msg.replies[0].text
    assert calls and calls[0]["exit_code"] == -2


@pytest.mark.asyncio
async def test_retrieval_timeout(settings):
    msg = FakeMessage(text="what?")
    runner = make_runner(raise_exc=subprocess.TimeoutExpired(cmd="claude", timeout=settings.claude_timeout_seconds))
    calls: list[dict[str, Any]] = []
    await handle_retrieval(
        message=msg,
        question="what?",
        settings=settings,
        prompt_template=PROMPT_TEMPLATE,
        record_call=lambda **kw: calls.append(kw),
        runner=runner,
    )
    assert "took too long" in msg.replies[0].text
    assert calls and calls[0]["timeout"] is True
    assert calls[0]["exit_code"] == -1


@pytest.mark.asyncio
async def test_retrieval_subprocess_nonzero_exit(settings):
    msg = FakeMessage(text="anything?")
    runner = make_runner(stdout="", stderr="boom", returncode=2)
    calls: list[dict[str, Any]] = []
    await handle_retrieval(
        message=msg,
        question="anything?",
        settings=settings,
        prompt_template=PROMPT_TEMPLATE,
        record_call=lambda **kw: calls.append(kw),
        runner=runner,
    )
    assert "couldn't get a clean answer" in msg.replies[0].text
    assert calls and calls[0]["exit_code"] == -3


@pytest.mark.asyncio
async def test_retrieval_strips_leading_question_mark(settings):
    msg = FakeMessage(text="?does sleep matter")
    runner = make_runner(stdout=make_envelope(GOOD_INNER))
    captured: dict[str, str] = {}

    def _runner(*args, **kwargs):
        captured["prompt"] = kwargs["input"]
        from tests.conftest import FakeCompleted
        return FakeCompleted(stdout=make_envelope(GOOD_INNER))

    await handle_retrieval(
        message=msg,
        question="?does sleep matter",
        settings=settings,
        prompt_template=PROMPT_TEMPLATE,
        runner=_runner,
    )
    assert "does sleep matter" in captured["prompt"]
    assert captured["prompt"].count("?does") == 0


@pytest.mark.asyncio
async def test_retrieval_empty_question_replies_prompt(settings):
    msg = FakeMessage(text="?")
    await handle_retrieval(
        message=msg,
        question="?",
        settings=settings,
        prompt_template=PROMPT_TEMPLATE,
    )
    assert "What would you like" in msg.replies[0].text


def test_render_prompt_substitutes_slots(tmp_path):
    template = "v={vault_dir} q={question}"
    out = claude_runner.render_prompt(template, question="hi", vault_dir=tmp_path)
    assert f"v={tmp_path}" in out
    assert "q=hi" in out


def test_load_prompt_template_reads_file(tmp_path):
    (tmp_path / "retrieve.md").write_text("hello", encoding="utf-8")
    assert claude_runner.load_prompt_template(tmp_path) == "hello"


def test_invoke_envelope_inner_dict_form():
    """If the envelope's `result` is already a dict, parse it directly."""
    inner = {"answer": "x", "sources": [], "quotes": [], "confidence": 0.5}
    runner = make_runner(stdout=__import__("json").dumps({"session_id": "s", "result": inner}))
    outcome = claude_runner.invoke(claude_bin="claude", prompt="p", timeout_seconds=1.0, runner=runner)
    assert outcome.session_id == "s"


def test_invoke_envelopeless_inner_only():
    inner = {"answer": "x", "sources": [], "quotes": [], "confidence": 0.5}
    runner = make_runner(stdout=__import__("json").dumps(inner))
    outcome = claude_runner.invoke(claude_bin="claude", prompt="p", timeout_seconds=1.0, runner=runner)
    assert outcome.session_id is None


def test_invoke_validates_source_path_no_leading_slash():
    inner = {
        "answer": "x",
        "sources": [{"path": "/abs/bad.md", "title": "t"}],
        "quotes": [],
        "confidence": 0.5,
    }
    runner = make_runner(stdout=make_envelope(inner))
    with pytest.raises(claude_runner.ClaudeMalformedJSONError):
        claude_runner.invoke(claude_bin="claude", prompt="p", timeout_seconds=1.0, runner=runner)


def test_invoke_validates_quote_index_in_range():
    inner = {
        "answer": "x",
        "sources": [{"path": "a/b.md", "title": "t"}],
        "quotes": [{"source_index": 7, "text": "x"}],
        "confidence": 0.5,
    }
    runner = make_runner(stdout=make_envelope(inner))
    with pytest.raises(claude_runner.ClaudeMalformedJSONError):
        claude_runner.invoke(claude_bin="claude", prompt="p", timeout_seconds=1.0, runner=runner)


def test_invoke_validates_confidence_range():
    inner = {"answer": "x", "sources": [], "quotes": [], "confidence": 1.7}
    runner = make_runner(stdout=make_envelope(inner))
    with pytest.raises(claude_runner.ClaudeMalformedJSONError):
        claude_runner.invoke(claude_bin="claude", prompt="p", timeout_seconds=1.0, runner=runner)


def test_invoke_truncates_long_quotes():
    inner = {
        "answer": "x",
        "sources": [{"path": "a/b.md", "title": "t"}],
        "quotes": [{"source_index": 0, "text": "x" * 500}],
        "confidence": 0.5,
    }
    runner = make_runner(stdout=make_envelope(inner))
    outcome = claude_runner.invoke(claude_bin="claude", prompt="p", timeout_seconds=1.0, runner=runner)
    assert len(outcome.quotes[0].text) <= 280


def test_invoke_missing_binary_raises_transient():
    def _runner(*a, **kw):
        raise FileNotFoundError("nope")

    with pytest.raises(claude_runner.ClaudeTransientError):
        claude_runner.invoke(claude_bin="claude", prompt="p", timeout_seconds=1.0, runner=_runner)


def test_invoke_envelope_with_usage_nest():
    """Tokens nested under `usage` should be picked up when top-level fields are missing."""
    import json
    inner = {"answer": "x", "sources": [], "quotes": [], "confidence": 0.5}
    envelope = json.dumps({"session_id": "s", "result": json.dumps(inner), "usage": {"input_tokens": 12, "output_tokens": 7}})
    runner = make_runner(stdout=envelope)
    outcome = claude_runner.invoke(claude_bin="claude", prompt="p", timeout_seconds=1.0, runner=runner)
    assert outcome.input_tokens == 12 and outcome.output_tokens == 7
