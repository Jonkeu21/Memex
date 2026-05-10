"""Cover every CLAUDE.md intent rule and rule-ordering."""
from __future__ import annotations

import pytest

from bot.intent import Decision, Intent, classify, classify_text
from tests.conftest import FakeAttachment, FakeMessage


@pytest.mark.parametrize(
    "text, expected_intent, expected_url",
    [
        ("https://example.com/article", Intent.CAPTURE_URL, "https://example.com/article"),
        ("   https://example.com/x   ", Intent.CAPTURE_URL, "https://example.com/x"),
    ],
)
def test_rule_2_bare_url(text, expected_intent, expected_url):
    decision = classify_text(text)
    assert decision.intent is expected_intent
    assert decision.url == expected_url
    assert decision.user_note is None


def test_rule_3_url_with_text_extracts_note():
    decision = classify_text("read this later https://example.com/x interesting")
    assert decision.intent is Intent.CAPTURE_URL
    assert decision.url == "https://example.com/x"
    assert decision.user_note == "read this later  interesting"


def test_rule_4_question_mark_suffix():
    decision = classify_text("what about my sleep last week?")
    # rule 4 hits even though rule 5 also matches -- rule 4 is checked first.
    assert decision.intent is Intent.RETRIEVAL


def test_rule_4_question_mark_after_trailing_whitespace():
    decision = classify_text("does sourdough fail at 28C?   \n")
    assert decision.intent is Intent.RETRIEVAL


@pytest.mark.parametrize(
    "text",
    [
        "what time is it",
        "What did I read about transformers",
        "find the recipe",
        "Recall my last grocery list",
        "remind me to buy milk",
        "show me ml papers",
    ],
)
def test_rule_5_question_word_prefix(text):
    decision = classify_text(text)
    assert decision.intent is Intent.RETRIEVAL


def test_rule_5_word_boundary_does_not_match_substring():
    # "whatever" begins with "what" but should not trigger rule 5; it should
    # fall through to rule 6 (capture text).
    decision = classify_text("whatever I do, it ends in pasta")
    assert decision.intent is Intent.CAPTURE_TEXT


def test_rule_6_default_text():
    decision = classify_text("just some plain notes about today")
    assert decision.intent is Intent.CAPTURE_TEXT


def test_classify_empty_text_defaults_to_capture():
    decision = classify_text("")
    assert decision.intent is Intent.CAPTURE_TEXT


def test_rule_1_attachment_wins_over_url_in_caption():
    """A document with a URL caption hits rule 1, not rule 3."""
    msg = FakeMessage(
        text="see https://example.com/foo",
        document=FakeAttachment(file_id="DOC1", file_size=10),
    )
    decision = classify(msg)
    assert decision.intent is Intent.CAPTURE_ATTACHMENT


def test_rule_1_voice_attachment():
    msg = FakeMessage(voice=FakeAttachment(file_id="V1"))
    assert classify(msg).intent is Intent.CAPTURE_ATTACHMENT


def test_rule_1_audio_attachment():
    msg = FakeMessage(audio=FakeAttachment(file_id="A1"))
    assert classify(msg).intent is Intent.CAPTURE_ATTACHMENT


def test_rule_1_video_attachment():
    msg = FakeMessage(video=FakeAttachment(file_id="VD1"))
    assert classify(msg).intent is Intent.CAPTURE_ATTACHMENT


def test_rule_1_photo_attachment():
    msg = FakeMessage(photo=[FakeAttachment(file_id="P1")])
    assert classify(msg).intent is Intent.CAPTURE_ATTACHMENT


def test_classify_falls_through_to_text_when_no_attachment():
    msg = FakeMessage(text="hello world")
    assert classify(msg).intent is Intent.CAPTURE_TEXT


def test_classify_handles_none_text():
    msg = FakeMessage(text=None)
    assert classify(msg).intent is Intent.CAPTURE_TEXT


def test_decision_dataclass_carries_text():
    decision = classify_text("plain note")
    assert decision.text == "plain note"
    assert decision.url is None
