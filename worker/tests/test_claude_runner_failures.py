"""Tests for the claude -p subprocess wrapper."""
from __future__ import annotations

import json
import subprocess

import pytest

from worker import claude_runner as cr
from worker.db import ClaudeTelemetry


def _ok_envelope(folder: str = "resources/ml-papers", confidence: float = 0.9) -> str:
    inner = {
        "folder": folder, "title": "Title", "summary": "Summ.", "tags": ["x"],
        "confidence": confidence,
    }
    return json.dumps({"session_id": "s1", "result": json.dumps(inner),
                       "input_tokens": 10, "output_tokens": 5})


class _FakeProc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_invoke_success():
    def runner(*a, **kw):
        return _FakeProc(stdout=_ok_envelope())
    out = cr.invoke(claude_bin="claude", prompt="p", timeout_seconds=5.0, runner=runner)
    assert out.folder == "resources/ml-papers"
    assert out.confidence == 0.9
    assert out.telemetry.input_tokens == 10
    assert out.telemetry.output_tokens == 5
    assert out.telemetry.session_id == "s1"


def test_invoke_nonzero_exit_transient():
    def runner(*a, **kw):
        return _FakeProc(stdout="", stderr="boom", returncode=2)
    with pytest.raises(cr.ClaudeTransientError):
        cr.invoke(claude_bin="claude", prompt="p", timeout_seconds=5.0, runner=runner)


def test_invoke_timeout_transient():
    def runner(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1.0)
    with pytest.raises(cr.ClaudeTransientError):
        cr.invoke(claude_bin="claude", prompt="p", timeout_seconds=1.0, runner=runner)


def test_invoke_binary_missing_transient():
    def runner(*a, **kw):
        raise FileNotFoundError("claude")
    with pytest.raises(cr.ClaudeTransientError):
        cr.invoke(claude_bin="claude", prompt="p", timeout_seconds=5.0, runner=runner)


def test_invoke_outer_malformed():
    def runner(*a, **kw):
        return _FakeProc(stdout="not json", returncode=0)
    with pytest.raises(cr.ClaudeMalformedJSONError):
        cr.invoke(claude_bin="claude", prompt="p", timeout_seconds=5.0, runner=runner)


def test_invoke_inner_malformed():
    bad = json.dumps({"session_id": "s1", "result": "not-json"})
    def runner(*a, **kw):
        return _FakeProc(stdout=bad, returncode=0)
    with pytest.raises(cr.ClaudeMalformedJSONError):
        cr.invoke(claude_bin="claude", prompt="p", timeout_seconds=5.0, runner=runner)


def test_invoke_inner_validation_missing_folder():
    inner = {"title": "t", "summary": "s", "tags": [], "confidence": 0.5}
    env = json.dumps({"result": json.dumps(inner)})
    def runner(*a, **kw):
        return _FakeProc(stdout=env, returncode=0)
    with pytest.raises(cr.ClaudeValidationError):
        cr.invoke(claude_bin="claude", prompt="p", timeout_seconds=5.0, runner=runner)


def test_invoke_inner_confidence_out_of_range():
    inner = {"folder": "f", "title": "t", "summary": "s", "tags": [], "confidence": 1.7}
    env = json.dumps({"result": json.dumps(inner)})
    def runner(*a, **kw):
        return _FakeProc(stdout=env, returncode=0)
    with pytest.raises(cr.ClaudeValidationError):
        cr.invoke(claude_bin="claude", prompt="p", timeout_seconds=5.0, runner=runner)


def test_invoke_inner_tags_not_strings():
    inner = {"folder": "f", "title": "t", "summary": "s", "tags": [1, 2], "confidence": 0.5}
    env = json.dumps({"result": json.dumps(inner)})
    def runner(*a, **kw):
        return _FakeProc(stdout=env, returncode=0)
    with pytest.raises(cr.ClaudeValidationError):
        cr.invoke(claude_bin="claude", prompt="p", timeout_seconds=5.0, runner=runner)


def test_invoke_empty_stdout():
    def runner(*a, **kw):
        return _FakeProc(stdout="", returncode=0)
    with pytest.raises(cr.ClaudeMalformedJSONError):
        cr.invoke(claude_bin="claude", prompt="p", timeout_seconds=5.0, runner=runner)


def test_invoke_envelope_with_usage_dict():
    inner = {"folder": "f", "title": "t", "summary": "s", "tags": [], "confidence": 0.5}
    env = json.dumps({
        "result": json.dumps(inner),
        "session_id": "abc",
        "usage": {"input_tokens": 7, "output_tokens": 3},
    })
    def runner(*a, **kw):
        return _FakeProc(stdout=env, returncode=0)
    out = cr.invoke(claude_bin="claude", prompt="p", timeout_seconds=5.0, runner=runner)
    assert out.telemetry.input_tokens == 7
    assert out.telemetry.output_tokens == 3


def test_invoke_inner_only_no_envelope():
    """If stdout itself is the inner JSON (no envelope), we accept it."""
    inner = {"folder": "f", "title": "t", "summary": "s", "tags": [], "confidence": 0.5}
    def runner(*a, **kw):
        return _FakeProc(stdout=json.dumps(inner), returncode=0)
    out = cr.invoke(claude_bin="claude", prompt="p", timeout_seconds=5.0, runner=runner)
    assert out.folder == "f"


def test_invoke_envelope_with_dict_result():
    inner = {"folder": "f", "title": "t", "summary": "s", "tags": [], "confidence": 0.5}
    env = json.dumps({"result": inner})
    def runner(*a, **kw):
        return _FakeProc(stdout=env, returncode=0)
    out = cr.invoke(claude_bin="claude", prompt="p", timeout_seconds=5.0, runner=runner)
    assert out.folder == "f"


def test_render_prompt_substitutes():
    template = "T:{taxonomy_yaml}|S:{source_type}|M:{source_metadata}|X:{extracted_text}"
    out = cr.render_prompt(template, taxonomy_yaml="YAML", source_type="text",
                           source_metadata={"a": 1}, extracted_text="hello")
    assert "YAML" in out and "text" in out and '{"a": 1}' in out and "hello" in out


def test_render_prompt_truncates_extracted_text():
    template = "{extracted_text}"
    long = "a" * 40_000
    out = cr.render_prompt(template, taxonomy_yaml="", source_type="text", source_metadata={}, extracted_text=long)
    assert "truncated" in out
    assert len(out) < 40_000 + 100
