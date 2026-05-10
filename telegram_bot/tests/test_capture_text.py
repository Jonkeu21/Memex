"""Plain-text capture handler."""
from __future__ import annotations

import json

import httpx
import pytest

from bot.handlers.capture_text import handle_capture_text
from tests.conftest import FakeMessage


@pytest.mark.asyncio
async def test_capture_text_forwards_full_body(client, mock_api):
    body = "this is a longer note. it has https://example.com inside but stays a text capture."
    msg = FakeMessage(text=body)
    await handle_capture_text(message=msg, text=body, client=client)
    assert mock_api.requests[0].url.path == "/captures/text"
    payload = json.loads(mock_api.requests[0].content)
    # The bot does NOT strip URLs from text-snippet captures.
    assert payload == {"text": body}
    assert msg.replies[0].text.startswith("✓ Queued #")
    assert "(text)" in msg.replies[0].text


@pytest.mark.asyncio
async def test_capture_text_empty_body_replies_without_api_call(client, mock_api):
    msg = FakeMessage(text="   ")
    await handle_capture_text(message=msg, text="   ", client=client)
    assert mock_api.requests == []
    assert "Nothing to capture" in msg.replies[0].text


@pytest.mark.asyncio
async def test_capture_text_5xx_safe_error_message(client, mock_api):
    mock_api.behaviour["/captures/text"] = httpx.Response(500)
    msg = FakeMessage(text="hello")
    await handle_capture_text(message=msg, text="hello", client=client)
    assert msg.replies[0].text.startswith("Sorry")
    assert "capture-token" not in msg.replies[0].text
