"""Attachment captures: voice / audio / document / video / photo."""
from __future__ import annotations

import httpx
import pytest

from bot.handlers.capture_attachment import handle_capture_attachment
from tests.conftest import FakeAttachment, FakeBot, FakeMessage


@pytest.mark.asyncio
async def test_capture_voice(client, mock_api, settings):
    bot = FakeBot(payloads={"V1": b"voice-bytes"})
    msg = FakeMessage(
        message_id=77,
        voice=FakeAttachment(file_id="V1", file_size=11, mime_type="audio/ogg"),
        _bot=bot,
    )
    await handle_capture_attachment(message=msg, settings=settings, client=client)
    req = mock_api.requests[0]
    assert req.url.path == "/captures/voice"
    assert req.headers["authorization"].startswith("Bearer ")
    body = req.content
    assert b"voice-bytes" in body
    assert b"voice_77.ogg" in body
    assert msg.replies[0].text.startswith("✓ Queued #")
    assert "(voice)" in msg.replies[0].text


@pytest.mark.asyncio
async def test_capture_audio_routes_to_voice_endpoint(client, mock_api, settings):
    bot = FakeBot(payloads={"A1": b"mp3"})
    msg = FakeMessage(
        message_id=88,
        audio=FakeAttachment(file_id="A1", file_size=3, mime_type="audio/mpeg", file_name="podcast.mp3"),
        _bot=bot,
    )
    await handle_capture_attachment(message=msg, settings=settings, client=client)
    assert mock_api.requests[0].url.path == "/captures/voice"
    assert b"podcast.mp3" in mock_api.requests[0].content


@pytest.mark.asyncio
async def test_capture_document(client, mock_api, settings):
    bot = FakeBot(payloads={"D1": b"%PDF-1.4 fake"})
    msg = FakeMessage(
        message_id=99,
        document=FakeAttachment(file_id="D1", file_size=12, mime_type="application/pdf", file_name="scan.pdf"),
        _bot=bot,
    )
    await handle_capture_attachment(message=msg, settings=settings, client=client)
    assert mock_api.requests[0].url.path == "/captures/file"
    assert b"scan.pdf" in mock_api.requests[0].content
    assert "(file)" in msg.replies[0].text


@pytest.mark.asyncio
async def test_capture_video(client, mock_api, settings):
    bot = FakeBot(payloads={"VD1": b"mp4-bytes"})
    msg = FakeMessage(
        message_id=100,
        video=FakeAttachment(file_id="VD1", file_size=9, mime_type="video/mp4"),
        _bot=bot,
    )
    await handle_capture_attachment(message=msg, settings=settings, client=client)
    assert mock_api.requests[0].url.path == "/captures/file"
    # Default video filename uses the message id.
    assert b"video_100.mp4" in mock_api.requests[0].content


@pytest.mark.asyncio
async def test_capture_photo_picks_largest(client, mock_api, settings):
    bot = FakeBot(payloads={"big": b"jpeg-big", "small": b"x"})
    photos = [
        FakeAttachment(file_id="small", file_size=10),
        FakeAttachment(file_id="big", file_size=999),
    ]
    msg = FakeMessage(message_id=55, photo=photos, _bot=bot)
    await handle_capture_attachment(message=msg, settings=settings, client=client)
    body = mock_api.requests[0].content
    # Only the largest payload is uploaded.
    assert b"jpeg-big" in body
    assert b"photo_55.jpg" in body


@pytest.mark.asyncio
async def test_capture_attachment_rejects_oversize_declared(client, mock_api, settings):
    huge = settings.max_download_bytes + 1
    msg = FakeMessage(
        document=FakeAttachment(file_id="D2", file_size=huge),
        _bot=FakeBot(),
    )
    await handle_capture_attachment(message=msg, settings=settings, client=client)
    assert mock_api.requests == []
    assert "Sorry" in msg.replies[0].text


@pytest.mark.asyncio
async def test_capture_attachment_5xx(client, mock_api, settings):
    mock_api.behaviour["/captures/file"] = httpx.Response(500)
    bot = FakeBot(payloads={"D1": b"x"})
    msg = FakeMessage(
        document=FakeAttachment(file_id="D1", file_size=1),
        _bot=bot,
    )
    await handle_capture_attachment(message=msg, settings=settings, client=client)
    assert msg.replies[0].text.startswith("Sorry")


@pytest.mark.asyncio
async def test_capture_attachment_no_recognised_attachment(client, mock_api, settings):
    msg = FakeMessage(text="oops")
    await handle_capture_attachment(message=msg, settings=settings, client=client)
    assert mock_api.requests == []
    assert "couldn't find" in msg.replies[0].text


@pytest.mark.asyncio
async def test_capture_attachment_telegram_download_failure(client, mock_api, settings):
    bot = FakeBot(raise_on_get_file=True)
    msg = FakeMessage(
        voice=FakeAttachment(file_id="V1", file_size=1),
        _bot=bot,
    )
    await handle_capture_attachment(message=msg, settings=settings, client=client)
    assert mock_api.requests == []
    assert "Sorry" in msg.replies[0].text
