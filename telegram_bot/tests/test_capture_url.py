"""URL capture handler."""
from __future__ import annotations

import json

import httpx
import pytest

from bot.handlers.capture_url import handle_capture_url
from bot.intent import Decision, Intent, classify_text
from tests.conftest import FakeMessage


@pytest.mark.asyncio
async def test_capture_url_posts_and_acks(client, mock_api):
    msg = FakeMessage(text="https://example.com/x")
    decision = classify_text(msg.text)
    await handle_capture_url(message=msg, decision=decision, client=client)
    assert mock_api.requests[0].url.path == "/captures/url"
    body = json.loads(mock_api.requests[0].content)
    assert body == {"url": "https://example.com/x"}
    assert mock_api.requests[0].headers["authorization"].startswith("Bearer ")
    assert msg.replies[0].text.startswith("✓ Queued #")
    assert "(url)" in msg.replies[0].text
    assert msg.replies[0].reply_to_message_id == msg.message_id


@pytest.mark.asyncio
async def test_capture_url_with_user_note(client, mock_api):
    msg = FakeMessage(text="read later https://example.com/y interesting bit")
    decision = classify_text(msg.text)
    await handle_capture_url(message=msg, decision=decision, client=client)
    body = json.loads(mock_api.requests[0].content)
    assert body["url"] == "https://example.com/y"
    assert "user_note" in body and "read later" in body["user_note"]


@pytest.mark.asyncio
async def test_capture_url_handles_5xx(client, mock_api):
    mock_api.behaviour["/captures/url"] = httpx.Response(500, json={"error": "boom"})
    msg = FakeMessage(text="https://example.com/x")
    decision = classify_text(msg.text)
    await handle_capture_url(message=msg, decision=decision, client=client)
    assert msg.replies[0].text.startswith("Sorry")
    # Token must not appear in user-facing message.
    assert "capture-token-zzz" not in msg.replies[0].text


@pytest.mark.asyncio
async def test_capture_url_handles_4xx(client, mock_api):
    mock_api.behaviour["/captures/url"] = httpx.Response(400, json={"error": "invalid"})
    msg = FakeMessage(text="https://bad.example.com")
    decision = classify_text(msg.text)
    await handle_capture_url(message=msg, decision=decision, client=client)
    assert msg.replies[0].text.startswith("Sorry")
