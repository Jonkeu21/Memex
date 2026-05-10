"""Render retrieval outcomes into Telegram messages.

Per CLAUDE.md "Telegram bot contract" → "Retrieval response schema":

- Message 1: the ``answer`` field, rendered as Markdown. If it exceeds 3500
  characters, split on paragraph boundaries into multiple messages numbered
  ``(1/n)``, ``(2/n)``, …
- Message 2: a "Sources" message listing each source as ``• <vault_path>``.
- Message 3: a "Quotes" message rendering each quote as a Telegram blockquote
  prefixed with the source's index.

If ``sources`` is empty, only Message 1 is sent and it ends with the literal
line ``_No sources found in vault._``.

The renderer also returns the rendered text rather than calling Telegram
directly so unit tests don't need a fake bot. The caller (handlers/retrieval.py)
posts each message in order.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .claude_runner import RetrievalOutcome, RetrievalQuote, RetrievalSource

ANSWER_CHUNK_CHAR_LIMIT = 3500
NO_SOURCES_MARKER = "_No sources found in vault._"


@dataclass(frozen=True)
class RenderedRetrieval:
    """Ordered list of Telegram message bodies to send sequentially."""

    messages: list[str]


def _split_paragraphs(text: str) -> list[str]:
    """Split on blank-line paragraph boundaries, preserving paragraph order.

    Empty paragraphs are dropped so we never emit a blank chunk. Trailing/
    leading whitespace inside a paragraph is preserved (callers may rely on
    leading code-fence markers).
    """
    parts = text.split("\n\n")
    return [p for p in parts if p.strip()]


def _is_fence_line(line: str) -> bool:
    return line.lstrip().startswith("```")


def _fence_open_after(text: str) -> bool:
    """Return True iff an odd number of fenced-code-block markers appear in text.

    A code fence is any line whose stripped form starts with ``` (CommonMark).
    Tracking parity tells us whether appending ``text`` would leave the
    chunk inside an open fence, in which case we must not split here.
    """
    count = 0
    for line in text.split("\n"):
        if _is_fence_line(line):
            count += 1
    return (count % 2) == 1


def chunk_answer(answer: str, *, limit: int = ANSWER_CHUNK_CHAR_LIMIT) -> list[str]:
    """Chunk the answer text on paragraph boundaries.

    Rules:
    - Never split inside an open code fence: a chunk that would end with an
      odd number of triple-backtick lines is extended until the fence closes.
    - A single paragraph longer than ``limit`` is emitted as its own chunk
      (Telegram's hard cap is 4096; ``limit`` defaults to 3500 with headroom).
    - Numbering "(i/n)" is added by ``_number_chunks`` after the split.
    """
    if not answer.strip():
        return [""]
    paragraphs = _split_paragraphs(answer)
    if not paragraphs:
        return [answer]

    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = para if not current else f"{current}\n\n{para}"
        # If adding this paragraph would push us over the limit AND the current
        # buffer has content AND the current buffer is not in an open code fence,
        # flush the current buffer first.
        if (
            current
            and len(candidate) > limit
            and not _fence_open_after(current)
        ):
            chunks.append(current)
            current = para
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _number_chunks(chunks: Sequence[str]) -> list[str]:
    if len(chunks) <= 1:
        return list(chunks)
    n = len(chunks)
    return [f"{chunk}\n\n({i + 1}/{n})" for i, chunk in enumerate(chunks)]


def render_answer_messages(outcome: RetrievalOutcome) -> list[str]:
    """Render the answer message(s).

    If sources is empty, append the no-sources marker to the final answer
    message (per CLAUDE.md).
    """
    body = outcome.answer.strip() or "_No answer._"
    chunks = chunk_answer(body)
    chunks = _number_chunks(chunks)
    if not outcome.sources:
        chunks[-1] = f"{chunks[-1]}\n\n{NO_SOURCES_MARKER}"
    return chunks


def render_sources_message(sources: Iterable[RetrievalSource]) -> str:
    """Render the "Sources" message.

    Each source becomes a single line ``• <vault_path>`` per CLAUDE.md.
    """
    lines = ["*Sources*"]
    for src in sources:
        lines.append(f"• {src.path}")
    return "\n".join(lines)


def render_quotes_message(
    quotes: Iterable[RetrievalQuote], sources: Sequence[RetrievalSource]
) -> str:
    """Render the "Quotes" message as Telegram blockquotes.

    Each quote is prefixed with its source's 1-based index. Telegram renders
    lines starting with ``>`` as blockquotes.
    """
    lines = ["*Quotes*"]
    for q in quotes:
        idx = q.source_index + 1
        # Render every line of the quote as a continuation of the blockquote
        # so Telegram preserves the visual block.
        body_lines = q.text.split("\n")
        lines.append(f"> [{idx}] {body_lines[0]}")
        for cont in body_lines[1:]:
            lines.append(f"> {cont}")
    return "\n".join(lines)


def render_confidence_caption(confidence: float) -> str:
    """Optional small caption for the answer's confidence."""
    return f"_filed at {confidence:.2f} confidence_"


def render_retrieval(outcome: RetrievalOutcome) -> RenderedRetrieval:
    """Top-level renderer producing the ordered message list."""
    messages = render_answer_messages(outcome)
    if outcome.sources:
        messages.append(render_sources_message(outcome.sources))
        if outcome.quotes:
            messages.append(render_quotes_message(outcome.quotes, outcome.sources))
    return RenderedRetrieval(messages=messages)


def acknowledgement(queue_id: int, source_type: str) -> str:
    """Render the capture acknowledgement per CLAUDE.md.

    Format: ``✓ Queued #4123 (url) — I'll let you know where it lands.``
    """
    return f"✓ Queued #{queue_id} ({source_type}) — I'll let you know where it lands."
