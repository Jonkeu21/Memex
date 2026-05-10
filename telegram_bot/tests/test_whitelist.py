"""Whitelist enforcement and silent rejection."""
from __future__ import annotations

import logging

import pytest

from bot.auth import is_allowed, log_rejection
from bot.logging import configure as configure_logging
from bot.main import dispatch, BotContext
from tests.conftest import FakeChat, FakeMessage, FakeUpdate


def test_is_allowed_membership():
    assert is_allowed(42, [42, 99]) is True
    assert is_allowed(7, [42, 99]) is False
    assert is_allowed(None, [42]) is False


def test_log_rejection_emits_warn(capsys):
    configure_logging("DEBUG")
    log_rejection(99)
    out = capsys.readouterr().out
    assert "chat_rejected" in out
    assert '"level":"warn"' in out


@pytest.mark.asyncio
async def test_dispatch_silently_drops_non_whitelisted(settings, client):
    msg = FakeMessage(chat=FakeChat(id=99), text="hi")
    update = FakeUpdate(message=msg)
    ctx = BotContext(settings=settings, client=client, prompt_template="x")
    await dispatch(update, ctx)
    # No reply emitted whatsoever.
    assert msg.replies == []


@pytest.mark.asyncio
async def test_dispatch_allows_whitelisted(settings, client, mock_api):
    msg = FakeMessage(chat=FakeChat(id=4242), text="plain text capture")
    update = FakeUpdate(message=msg)
    ctx = BotContext(settings=settings, client=client, prompt_template="x")
    await dispatch(update, ctx)
    assert len(msg.replies) == 1
    assert msg.replies[0].text.startswith("✓ Queued")
    assert mock_api.requests[0].url.path == "/captures/text"
