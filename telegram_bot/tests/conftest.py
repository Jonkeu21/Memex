"""Test fixtures: fake Telegram updates, mock capture API, config helpers."""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

# Make the bot package importable when pytest is invoked from telegram_bot/.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.capture_client import CaptureClient
from bot.config import Settings


# ---------- Fake Telegram message types ----------

@dataclass
class FakeChat:
    id: int = 4242


@dataclass
class FakeFile:
    """Stand-in for telegram.File returned by Bot.get_file."""
    payload: bytes = b"hello"

    async def download_to_memory(self, *, out: BytesIO) -> None:
        out.write(self.payload)


@dataclass
class FakeBot:
    """Stand-in for telegram.Bot.get_file."""
    payloads: dict[str, bytes] = field(default_factory=dict)
    raise_on_get_file: bool = False

    async def get_file(self, file_id: str) -> FakeFile:
        if self.raise_on_get_file:
            raise RuntimeError("simulated telegram failure")
        return FakeFile(payload=self.payloads.get(file_id, b"hello"))


@dataclass
class FakeReply:
    text: str
    reply_to_message_id: int | None
    parse_mode: str | None


@dataclass
class FakeAttachment:
    """Generic stand-in for voice/audio/document/video PhotoSize."""
    file_id: str = "AgADBg"
    file_size: int | None = 1024
    mime_type: str | None = None
    file_name: str | None = None


@dataclass
class FakeMessage:
    chat: FakeChat = field(default_factory=FakeChat)
    message_id: int = 1
    text: str | None = None
    voice: FakeAttachment | None = None
    audio: FakeAttachment | None = None
    document: FakeAttachment | None = None
    video: FakeAttachment | None = None
    photo: list[FakeAttachment] = field(default_factory=list)
    _bot: FakeBot | None = None
    replies: list[FakeReply] = field(default_factory=list)

    def get_bot(self) -> FakeBot:
        if self._bot is None:
            self._bot = FakeBot()
        return self._bot

    async def reply_text(
        self,
        text: str,
        *,
        reply_to_message_id: int | None = None,
        parse_mode: str | None = None,
    ) -> None:
        self.replies.append(
            FakeReply(text=text, reply_to_message_id=reply_to_message_id, parse_mode=parse_mode)
        )


@dataclass
class FakeUpdate:
    message: FakeMessage | None
    effective_message: FakeMessage | None = None
    effective_chat: FakeChat | None = None

    def __post_init__(self) -> None:
        if self.effective_message is None:
            self.effective_message = self.message
        if self.effective_chat is None and self.message is not None:
            self.effective_chat = self.message.chat


# ---------- Settings fixture ----------

@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        bot_token="bot-token-xxx",
        allowed_chat_ids=frozenset({4242}),
        capture_api_base_url="http://capture-test:8001",
        capture_api_token="capture-token-zzz",
        vault_dir=tmp_path / "vault",
        db_path=tmp_path / "memex.db",
        claude_bin="claude",
        claude_timeout_seconds=10.0,
        max_download_mb=25,
        log_level="DEBUG",
    )


# ---------- Mock capture API via httpx.MockTransport ----------

@dataclass
class MockCaptureAPI:
    """Records every request, returns canned responses keyed by path."""
    requests: list[httpx.Request] = field(default_factory=list)
    next_id: int = 4100
    behaviour: dict[str, Any] = field(default_factory=dict)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        override = self.behaviour.get(path)
        if isinstance(override, httpx.Response):
            return override
        if callable(override):
            return override(request)
        # Default: 202 with a fresh ack id.
        self.next_id += 1
        return httpx.Response(
            202,
            json={"id": self.next_id, "status": "queued", "created_at": "2026-05-10T14:22:01.123456Z"},
        )


@pytest.fixture
def mock_api() -> MockCaptureAPI:
    return MockCaptureAPI()


@pytest.fixture
async def client(mock_api, settings):
    transport = httpx.MockTransport(mock_api.handler)
    c = CaptureClient(
        base_url=settings.capture_api_base_url,
        token=settings.capture_api_token,
        transport=transport,
    )
    try:
        yield c
    finally:
        await c.aclose()


# ---------- Helpers ----------

def make_envelope(inner: dict[str, Any], *, session_id: str = "sess-1",
                  input_tokens: int = 100, output_tokens: int = 50) -> str:
    return json.dumps({
        "session_id": session_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "result": json.dumps(inner),
    })


@dataclass
class FakeCompleted:
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


def make_runner(stdout: str = "", stderr: str = "", returncode: int = 0,
                raise_exc: BaseException | None = None) -> Callable[..., FakeCompleted]:
    def _runner(*args: Any, **kwargs: Any) -> FakeCompleted:
        if raise_exc is not None:
            raise raise_exc
        return FakeCompleted(stdout=stdout, stderr=stderr, returncode=returncode)
    return _runner
