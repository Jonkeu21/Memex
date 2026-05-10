"""End-to-end dispatch via main.dispatch covering each intent path."""
from __future__ import annotations

import json

import pytest

from bot.main import BotContext, dispatch
from tests.conftest import (
    FakeAttachment,
    FakeBot,
    FakeChat,
    FakeMessage,
    FakeUpdate,
    make_envelope,
    make_runner,
)


@pytest.mark.asyncio
async def test_dispatch_url_intent(settings, client, mock_api):
    msg = FakeMessage(text="https://example.com/article")
    ctx = BotContext(settings=settings, client=client, prompt_template="t")
    await dispatch(FakeUpdate(message=msg), ctx)
    assert mock_api.requests[0].url.path == "/captures/url"


@pytest.mark.asyncio
async def test_dispatch_text_intent(settings, client, mock_api):
    msg = FakeMessage(text="just a note")
    ctx = BotContext(settings=settings, client=client, prompt_template="t")
    await dispatch(FakeUpdate(message=msg), ctx)
    assert mock_api.requests[0].url.path == "/captures/text"


@pytest.mark.asyncio
async def test_dispatch_attachment_intent(settings, client, mock_api):
    bot = FakeBot(payloads={"V1": b"v"})
    msg = FakeMessage(voice=FakeAttachment(file_id="V1", file_size=1), _bot=bot)
    ctx = BotContext(settings=settings, client=client, prompt_template="t")
    await dispatch(FakeUpdate(message=msg), ctx)
    assert mock_api.requests[0].url.path == "/captures/voice"


@pytest.mark.asyncio
async def test_dispatch_retrieval_intent(settings, client, mock_api, monkeypatch):
    inner = {"answer": "answer body", "sources": [], "quotes": [], "confidence": 0.4}
    runner = make_runner(stdout=make_envelope(inner))
    # Patch the claude_runner.invoke used by the retrieval handler so it picks
    # up our injected runner via asyncio.to_thread.
    from bot import claude_runner
    real_invoke = claude_runner.invoke
    monkeypatch.setattr(
        claude_runner, "invoke",
        lambda **kw: real_invoke(**{**kw, "runner": runner}),
    )
    msg = FakeMessage(text="what about my sleep?")
    ctx = BotContext(settings=settings, client=client, prompt_template="t={question}")
    await dispatch(FakeUpdate(message=msg), ctx)
    assert any("answer body" in r.text for r in msg.replies)


@pytest.mark.asyncio
async def test_dispatch_drops_non_whitelisted(settings, client, mock_api):
    msg = FakeMessage(chat=FakeChat(id=999), text="hello")
    ctx = BotContext(settings=settings, client=client, prompt_template="t")
    await dispatch(FakeUpdate(message=msg), ctx)
    assert msg.replies == []
    assert mock_api.requests == []
