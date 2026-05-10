"""Renderer chunking + answer/sources/quotes formatting."""
from __future__ import annotations

from bot import rendering
from bot.claude_runner import RetrievalOutcome, RetrievalQuote, RetrievalSource


def _outcome(answer: str = "ok", sources=None, quotes=None, confidence: float = 0.7) -> RetrievalOutcome:
    return RetrievalOutcome(
        answer=answer,
        sources=sources or [],
        quotes=quotes or [],
        confidence=confidence,
        session_id="s",
        input_tokens=10,
        output_tokens=5,
        duration_ms=100,
        exit_code=0,
    )


def test_short_answer_one_chunk():
    chunks = rendering.chunk_answer("hello\n\nworld", limit=3500)
    assert chunks == ["hello\n\nworld"]


def test_long_answer_splits_at_paragraph_boundary():
    para = "x" * 1000
    answer = "\n\n".join([para] * 5)  # ~5000 chars
    chunks = rendering.chunk_answer(answer, limit=3500)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 3500
        # No chunk starts with empty paragraph.
        assert chunk.strip()


def test_8000_char_answer_fits_under_4096():
    para = "y" * 700
    answer = "\n\n".join([para] * 11)  # ~7700 chars body, 8000+ with separators
    chunks = rendering.chunk_answer(answer, limit=3500)
    assert all(len(c) <= 4096 for c in chunks)


def test_render_answer_messages_numbered_when_multi_chunk():
    para = "z" * 1500
    answer = "\n\n".join([para] * 4)
    out = _outcome(answer=answer, sources=[RetrievalSource("a/b.md", "t")])
    msgs = rendering.render_answer_messages(out)
    assert len(msgs) >= 2
    n = len(msgs)
    for i, m in enumerate(msgs):
        assert f"({i + 1}/{n})" in m


def test_render_answer_messages_no_numbering_for_single_chunk():
    out = _outcome(answer="short", sources=[RetrievalSource("a/b.md", "t")])
    msgs = rendering.render_answer_messages(out)
    assert len(msgs) == 1
    assert "(1/1)" not in msgs[0]


def test_no_sources_marker_appended_to_last_chunk():
    out = _outcome(answer="brief", sources=[], quotes=[])
    msgs = rendering.render_answer_messages(out)
    assert msgs[-1].endswith("_No sources found in vault._")


def test_no_sources_marker_with_long_answer_only_on_last():
    para = "q" * 1500
    out = _outcome(answer="\n\n".join([para] * 4), sources=[])
    msgs = rendering.render_answer_messages(out)
    assert msgs[-1].endswith("_No sources found in vault._")
    for m in msgs[:-1]:
        assert "_No sources found in vault._" not in m


def test_chunker_does_not_split_inside_open_code_fence():
    """A code fence opened in one paragraph and closed several paragraphs later
    must end up in the same chunk so the fence doesn't break."""
    fenced = "```python\n" + ("print(1)\n" * 200) + "```"
    answer = "intro paragraph\n\n" + fenced + "\n\nafter paragraph"
    chunks = rendering.chunk_answer(answer, limit=3500)
    # Every chunk must have an even number of fence lines (no chunk leaves an
    # open fence).
    for chunk in chunks:
        fence_count = sum(1 for line in chunk.split("\n") if line.lstrip().startswith("```"))
        assert fence_count % 2 == 0, f"chunk left an open fence: {chunk[:80]!r}"


def test_render_sources_message_format():
    out = _outcome(
        sources=[
            RetrievalSource("areas/health/x.md", "X"),
            RetrievalSource("resources/y.md", "Y"),
        ]
    )
    rendered = rendering.render_retrieval(out)
    assert "*Sources*" in rendered.messages[1]
    assert "• areas/health/x.md" in rendered.messages[1]
    assert "• resources/y.md" in rendered.messages[1]


def test_render_quotes_message_blockquotes():
    sources = [RetrievalSource("a.md", "A"), RetrievalSource("b.md", "B")]
    quotes = [
        RetrievalQuote(0, "first verbatim"),
        RetrievalQuote(1, "second\nsecond-line"),
    ]
    out = _outcome(sources=sources, quotes=quotes, answer="hi")
    rendered = rendering.render_retrieval(out)
    msg = rendered.messages[2]
    assert "*Quotes*" in msg
    assert "> [1] first verbatim" in msg
    assert "> [2] second" in msg
    # Continuation lines also stay blockquoted.
    assert "> second-line" in msg


def test_render_retrieval_no_sources_only_one_message():
    out = _outcome(answer="x", sources=[])
    rendered = rendering.render_retrieval(out)
    assert len(rendered.messages) == 1


def test_render_retrieval_sources_no_quotes_omits_quotes_message():
    out = _outcome(answer="x", sources=[RetrievalSource("a.md", "t")], quotes=[])
    rendered = rendering.render_retrieval(out)
    assert len(rendered.messages) == 2  # answer + sources only


def test_acknowledgement_format():
    assert rendering.acknowledgement(4123, "url") == "✓ Queued #4123 (url) — I'll let you know where it lands."


def test_render_confidence_caption():
    out = _outcome(confidence=0.74)
    assert rendering.render_confidence_caption(out.confidence) == "_filed at 0.74 confidence_"


def test_chunker_handles_empty_answer():
    chunks = rendering.chunk_answer("")
    assert chunks == [""]


def test_chunker_handles_answer_with_only_whitespace():
    chunks = rendering.chunk_answer("\n\n   \n\n")
    # No paragraphs → original returned.
    assert len(chunks) == 1
