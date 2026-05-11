"""Retrieval router tests.

Mocks ``backend.routers.retrieval.invoke`` (via the ``app.state.claude_runner_invoke``
hook) so the suite never spawns ``claude -p``.
"""
from __future__ import annotations

import sqlite3
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.claude_runner import (
    ClaudeMalformedJSONError,
    ClaudeNotAuthenticatedError,
    ClaudeTimeoutError,
    ClaudeTransientError,
    RetrievalOutcome,
    RetrievalQuote,
    RetrievalSource,
)


def _ok_outcome(**overrides) -> RetrievalOutcome:
    base = dict(
        answer="The vault has notes on RoPE scaling.",
        sources=[RetrievalSource(path="resources/ml-papers/rope.md", title="RoPE")],
        quotes=[RetrievalQuote(source_index=0, text="Position interpolation degrades smoothly past 4× context.")],
        confidence=0.74,
        session_id="sess-abc",
        input_tokens=120,
        output_tokens=80,
        duration_ms=1234,
        exit_code=0,
        raw_envelope={"session_id": "sess-abc"},
    )
    base.update(overrides)
    return RetrievalOutcome(**base)


def _install_runner(client: TestClient, outcome_or_exc) -> None:
    def fake_invoke(**kwargs):
        if isinstance(outcome_or_exc, BaseException):
            raise outcome_or_exc
        return outcome_or_exc

    client.app.state.claude_runner_invoke = fake_invoke


def test_retrieval_happy_path(client: TestClient, auth_headers, vault_dir: Path) -> None:
    target = vault_dir / "resources" / "ml-papers" / "rope.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("---\nid: 1\n---\n# rope\n", encoding="utf-8")
    _install_runner(client, _ok_outcome())
    resp = client.post(
        "/api/v1/retrieval",
        headers=auth_headers,
        json={"question": "How does RoPE scale?"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"].startswith("The vault has notes")
    assert len(body["sources"]) == 1
    assert body["sources"][0]["exists"] is True
    assert body["confidence"] == 0.74
    assert body["session_id"] == "sess-abc"


def test_retrieval_marks_missing_sources(client: TestClient, auth_headers) -> None:
    _install_runner(client, _ok_outcome(
        sources=[RetrievalSource(path="resources/ml-papers/missing.md", title="missing")]
    ))
    resp = client.post(
        "/api/v1/retrieval",
        headers=auth_headers,
        json={"question": "anything?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sources"][0]["exists"] is False


def test_retrieval_records_telemetry(client: TestClient, auth_headers, db_path: Path) -> None:
    _install_runner(client, _ok_outcome())
    resp = client.post(
        "/api/v1/retrieval",
        headers=auth_headers,
        json={"question": "tell me"},
    )
    assert resp.status_code == 200
    conn = sqlite3.connect(db_path)
    rows = list(conn.execute(
        "SELECT service, purpose, exit_code, session_id FROM claude_calls"
    ))
    conn.close()
    assert len(rows) == 1
    service, purpose, exit_code, sess = rows[0]
    assert service == "dashboard"
    assert purpose == "retrieve"
    assert exit_code == 0
    assert sess == "sess-abc"


def test_retrieval_timeout_returns_504(client: TestClient, auth_headers) -> None:
    _install_runner(client, ClaudeTimeoutError("timed out after 5.0s"))
    resp = client.post(
        "/api/v1/retrieval",
        headers=auth_headers,
        json={"question": "slow"},
    )
    assert resp.status_code == 504
    assert resp.json()["detail"]["error"]["code"] == "retrieval_timeout"


def test_retrieval_unauthenticated_returns_503(client: TestClient, auth_headers) -> None:
    _install_runner(client, ClaudeNotAuthenticatedError("not logged in"))
    resp = client.post(
        "/api/v1/retrieval",
        headers=auth_headers,
        json={"question": "x"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["error"]["code"] == "claude_not_authenticated"


def test_retrieval_malformed_json_returns_502(client: TestClient, auth_headers) -> None:
    _install_runner(client, ClaudeMalformedJSONError("bad parse"))
    resp = client.post(
        "/api/v1/retrieval",
        headers=auth_headers,
        json={"question": "x"},
    )
    assert resp.status_code == 502
    assert resp.json()["detail"]["error"]["code"] == "malformed_response"


def test_retrieval_transient_returns_502(client: TestClient, auth_headers) -> None:
    _install_runner(client, ClaudeTransientError("nope"))
    resp = client.post(
        "/api/v1/retrieval",
        headers=auth_headers,
        json={"question": "x"},
    )
    assert resp.status_code == 502


def test_retrieval_blank_question_rejected(client: TestClient, auth_headers) -> None:
    resp = client.post(
        "/api/v1/retrieval",
        headers=auth_headers,
        json={"question": "   "},
    )
    assert resp.status_code == 422


def test_retrieval_oversize_question_rejected(client: TestClient, auth_headers) -> None:
    resp = client.post(
        "/api/v1/retrieval",
        headers=auth_headers,
        json={"question": "x" * 11_000},
    )
    assert resp.status_code == 422


def test_retrieval_missing_prompt_returns_500(client: TestClient, auth_headers) -> None:
    client.app.state.settings.retrieval_prompt_path.unlink()
    _install_runner(client, _ok_outcome())
    resp = client.post(
        "/api/v1/retrieval",
        headers=auth_headers,
        json={"question": "x"},
    )
    assert resp.status_code == 500
    assert resp.json()["detail"]["error"]["code"] == "prompt_unreadable"


def test_retrieval_falls_back_to_real_invoke_when_state_is_none(
    client: TestClient, auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production wiring: ``app.state.claude_runner_invoke`` is initialised to
    ``None`` and only test code overwrites it. The router must fall through to
    the module-level ``invoke`` symbol in that case rather than calling
    ``None`` (which raises ``TypeError: 'NoneType' object is not callable``
    and produces a bare 500 with no error envelope).
    """
    assert client.app.state.claude_runner_invoke is None  # baseline

    calls: list[dict] = []

    def fake_invoke(*, claude_bin, prompt, timeout_seconds):
        calls.append({"claude_bin": claude_bin, "timeout_seconds": timeout_seconds})
        return _ok_outcome()

    import backend.routers.retrieval as retrieval_module

    monkeypatch.setattr(retrieval_module, "invoke", fake_invoke)
    resp = client.post(
        "/api/v1/retrieval",
        headers=auth_headers,
        json={"question": "did the fallback fire?"},
    )
    assert resp.status_code == 200, resp.text
    assert len(calls) == 1
    assert calls[0]["claude_bin"] == "/usr/local/bin/claude-fake"


# ── claude_runner unit tests ────────────────────────────────────────────────

def test_claude_runner_parses_envelope_with_string_result() -> None:
    from backend.claude_runner import _parse_envelope

    inner, outer = _parse_envelope(
        '{"session_id":"s1","result":"{\\"answer\\":\\"hi\\",\\"sources\\":[],\\"quotes\\":[],\\"confidence\\":0.5}"}'
    )
    assert inner["answer"] == "hi"
    assert outer["session_id"] == "s1"


def test_claude_runner_parses_envelope_with_dict_result() -> None:
    from backend.claude_runner import _parse_envelope

    inner, outer = _parse_envelope(
        '{"session_id":"s2","result":{"answer":"hi","sources":[],"quotes":[],"confidence":0.5}}'
    )
    assert inner["answer"] == "hi"
    assert outer["session_id"] == "s2"


def test_claude_runner_rejects_bad_inner() -> None:
    from backend.claude_runner import _validate_inner

    with pytest.raises(ClaudeMalformedJSONError):
        _validate_inner({"answer": 1, "sources": [], "quotes": [], "confidence": 0.5})


def test_claude_runner_quote_truncation() -> None:
    from backend.claude_runner import _truncate_quote, QUOTE_MAX_CHARS

    long = "x" * (QUOTE_MAX_CHARS + 50)
    truncated = _truncate_quote(long)
    assert len(truncated) == QUOTE_MAX_CHARS
    assert truncated.endswith("…")


def test_claude_runner_invoke_timeout() -> None:
    from backend.claude_runner import invoke

    def slow_runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=0.1)

    with pytest.raises(ClaudeTimeoutError):
        invoke(claude_bin="x", prompt="p", timeout_seconds=0.1, runner=slow_runner)


def test_claude_runner_invoke_missing_binary() -> None:
    from backend.claude_runner import invoke

    def missing_runner(*args, **kwargs):
        raise FileNotFoundError("no such binary")

    with pytest.raises(ClaudeTransientError, match="claude binary not found"):
        invoke(claude_bin="x", prompt="p", timeout_seconds=1.0, runner=missing_runner)


def test_claude_runner_invoke_auth_error() -> None:
    from backend.claude_runner import invoke

    class FakeResult:
        returncode = 1
        stdout = ""
        stderr = "Error: please run claude /login"

    def runner(*args, **kwargs):
        return FakeResult()

    with pytest.raises(ClaudeNotAuthenticatedError):
        invoke(claude_bin="x", prompt="p", timeout_seconds=1.0, runner=runner)


def test_claude_runner_invoke_other_nonzero() -> None:
    from backend.claude_runner import invoke

    class FakeResult:
        returncode = 2
        stdout = ""
        stderr = "boom"

    def runner(*args, **kwargs):
        return FakeResult()

    with pytest.raises(ClaudeTransientError, match="exited 2"):
        invoke(claude_bin="x", prompt="p", timeout_seconds=1.0, runner=runner)


def test_claude_runner_invoke_happy_path_with_runner() -> None:
    from backend.claude_runner import invoke

    class FakeResult:
        returncode = 0
        stderr = ""
        stdout = (
            '{"session_id":"s9","input_tokens":11,"output_tokens":22,'
            '"result":{"answer":"hi","sources":[],"quotes":[],"confidence":0.5}}'
        )

    def runner(*args, **kwargs):
        return FakeResult()

    out = invoke(claude_bin="x", prompt="p", timeout_seconds=1.0, runner=runner)
    assert out.answer == "hi"
    assert out.session_id == "s9"
    assert out.input_tokens == 11


def test_claude_runner_invoke_usage_nest() -> None:
    """Some envelope shapes nest token counts under usage."""
    from backend.claude_runner import invoke

    class FakeResult:
        returncode = 0
        stderr = ""
        stdout = (
            '{"session_id":"s9","usage":{"input_tokens":1,"output_tokens":2},'
            '"result":{"answer":"","sources":[],"quotes":[],"confidence":0.0}}'
        )

    out = invoke(claude_bin="x", prompt="p", timeout_seconds=1.0, runner=lambda *a, **k: FakeResult())
    assert out.input_tokens == 1
    assert out.output_tokens == 2


def test_render_prompt_substitutes_slots() -> None:
    from backend.claude_runner import render_prompt

    template = "Vault: {vault_dir}\nQuestion: {question}\n"
    out = render_prompt(template, question="hi", vault_dir=Path("/vault"))
    assert "Vault: /vault" in out
    assert "Question: hi" in out


def test_load_prompt_template(tmp_path: Path) -> None:
    from backend.claude_runner import load_prompt_template

    p = tmp_path / "p.md"
    p.write_text("hello", encoding="utf-8")
    assert load_prompt_template(p) == "hello"


def test_parse_envelope_rejects_empty() -> None:
    from backend.claude_runner import _parse_envelope

    with pytest.raises(ClaudeMalformedJSONError, match="empty"):
        _parse_envelope("")


def test_parse_envelope_rejects_non_json() -> None:
    from backend.claude_runner import _parse_envelope

    with pytest.raises(ClaudeMalformedJSONError):
        _parse_envelope("not json at all")


def test_parse_envelope_rejects_array() -> None:
    from backend.claude_runner import _parse_envelope

    with pytest.raises(ClaudeMalformedJSONError):
        _parse_envelope("[1, 2, 3]")


def test_parse_envelope_rejects_unexpected_result_type() -> None:
    from backend.claude_runner import _parse_envelope

    with pytest.raises(ClaudeMalformedJSONError):
        _parse_envelope('{"result": 42}')


def test_parse_envelope_rejects_bad_inner_string() -> None:
    from backend.claude_runner import _parse_envelope

    with pytest.raises(ClaudeMalformedJSONError, match="inner parse"):
        _parse_envelope('{"result": "not-json"}')


@pytest.mark.parametrize(
    "bad",
    [
        # Wrong types or missing keys
        {"sources": [], "quotes": [], "confidence": 0.5},
        {"answer": "", "quotes": [], "confidence": 0.5},
        {"answer": "", "sources": [], "confidence": 0.5},
        {"answer": "", "sources": [], "quotes": []},
        {"answer": "", "sources": "x", "quotes": [], "confidence": 0.5},
        {"answer": "", "sources": [], "quotes": "x", "confidence": 0.5},
        {"answer": "", "sources": [], "quotes": [], "confidence": "high"},
        # Confidence out of range
        {"answer": "", "sources": [], "quotes": [], "confidence": 1.5},
        {"answer": "", "sources": [], "quotes": [], "confidence": -0.1},
        # Bad source
        {"answer": "", "sources": [{"path": "/abs", "title": "x"}], "quotes": [], "confidence": 0.0},
        {"answer": "", "sources": [{"path": "", "title": "x"}], "quotes": [], "confidence": 0.0},
        # Bad quote
        {"answer": "", "sources": [{"path": "p", "title": "t"}], "quotes": [{"source_index": 5, "text": "x"}], "confidence": 0.0},
        {"answer": "", "sources": [{"path": "p", "title": "t"}], "quotes": [{"source_index": -1, "text": "x"}], "confidence": 0.0},
        {"answer": "", "sources": [{"path": "p", "title": "t"}], "quotes": [{"source_index": True, "text": "x"}], "confidence": 0.0},
    ],
)
def test_validate_inner_rejects_bad(bad) -> None:
    from backend.claude_runner import _validate_inner

    with pytest.raises(ClaudeMalformedJSONError):
        _validate_inner(bad)


def test_validate_inner_accepts_minimal() -> None:
    from backend.claude_runner import _validate_inner

    answer, sources, quotes, conf = _validate_inner(
        {"answer": "", "sources": [], "quotes": [], "confidence": 0.0}
    )
    assert answer == ""
    assert sources == []
    assert quotes == []
    assert conf == 0.0
