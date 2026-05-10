"""Telegram bot entry point.

Wires the whitelist middleware, intent dispatcher, capture API client, and
``claude -p`` retrieval loop into a single python-telegram-bot Application.
Uses long polling: the bot is the only component allowed to make outbound
calls to the public internet, and webhooks would require exposing an HTTP
endpoint we don't otherwise need.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from .auth import is_allowed, log_rejection
from .capture_client import CaptureClient
from .claude_runner import load_prompt_template
from .config import Settings, load_settings
from .handlers.capture_attachment import handle_capture_attachment
from .handlers.capture_text import handle_capture_text
from .handlers.capture_url import handle_capture_url
from .handlers.commands import (
    cmd_capture,
    cmd_find,
    cmd_help,
    cmd_last,
    cmd_queue,
    cmd_start,
)
from .handlers.retrieval import handle_retrieval
from .intent import Decision, Intent, classify
from .logging import configure as configure_logging
from .logging import hash_chat_id, log_event
from .telemetry import record_claude_call

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class BotContext:
    """Container the application stores so handlers can reach shared state."""

    def __init__(
        self,
        settings: Settings,
        client: CaptureClient,
        prompt_template: str,
    ) -> None:
        self.settings = settings
        self.client = client
        self.prompt_template = prompt_template

    def record_call(self, **kwargs: Any) -> None:
        record_claude_call(self.settings.db_path, **kwargs)


def _chat_id_of(update: Any) -> int | None:
    msg = getattr(update, "effective_message", None) or getattr(update, "message", None)
    chat = getattr(msg, "chat", None) if msg else None
    if chat is None:
        chat = getattr(update, "effective_chat", None)
    cid = getattr(chat, "id", None)
    return int(cid) if cid is not None else None


async def dispatch(update: Any, app_ctx: BotContext) -> None:
    """Dispatch a non-command update to the right handler.

    Whitelist enforcement is checked here so every code path is covered.
    """
    chat_id = _chat_id_of(update)
    if not is_allowed(chat_id, app_ctx.settings.allowed_chat_ids):
        log_rejection(chat_id)
        return

    message = getattr(update, "effective_message", None) or getattr(update, "message", None)
    if message is None:
        return

    decision: Decision = classify(message)
    log_event(
        "message_received",
        intent=decision.intent.value,
        submitter_hash=hash_chat_id(chat_id if chat_id is not None else "unknown"),
    )

    if decision.intent is Intent.CAPTURE_ATTACHMENT:
        await handle_capture_attachment(
            message=message,
            settings=app_ctx.settings,
            client=app_ctx.client,
        )
    elif decision.intent is Intent.CAPTURE_URL:
        await handle_capture_url(
            message=message, decision=decision, client=app_ctx.client
        )
    elif decision.intent is Intent.RETRIEVAL:
        await handle_retrieval(
            message=message,
            question=decision.text or "",
            settings=app_ctx.settings,
            prompt_template=app_ctx.prompt_template,
            record_call=app_ctx.record_call,
        )
    else:
        await handle_capture_text(
            message=message, text=decision.text or "", client=app_ctx.client
        )


async def _whitelisted_command(update: Any, allowed: frozenset[int]) -> Any | None:
    chat_id = _chat_id_of(update)
    if not is_allowed(chat_id, allowed):
        log_rejection(chat_id)
        return None
    return getattr(update, "effective_message", None) or getattr(update, "message", None)


def build_application(settings: Settings, client: CaptureClient, prompt_template: str) -> Any:
    """Build a python-telegram-bot Application with all handlers wired.

    Imported lazily so the test suite does not depend on python-telegram-bot
    being installed; tests exercise handlers directly.
    """
    from telegram.ext import (  # type: ignore
        Application,
        CommandHandler,
        MessageHandler,
        filters,
    )

    app_ctx = BotContext(settings=settings, client=client, prompt_template=prompt_template)
    application = Application.builder().token(settings.bot_token).build()
    application.bot_data["memex"] = app_ctx

    async def _start(update, _ctx):
        m = await _whitelisted_command(update, settings.allowed_chat_ids)
        if m: await cmd_start(m)

    async def _help(update, _ctx):
        m = await _whitelisted_command(update, settings.allowed_chat_ids)
        if m: await cmd_help(m)

    async def _queue(update, _ctx):
        m = await _whitelisted_command(update, settings.allowed_chat_ids)
        if m: await cmd_queue(m, settings=app_ctx.settings)

    async def _last(update, _ctx):
        m = await _whitelisted_command(update, settings.allowed_chat_ids)
        if m: await cmd_last(m, settings=app_ctx.settings)

    async def _find(update, _ctx):
        m = await _whitelisted_command(update, settings.allowed_chat_ids)
        if m:
            await cmd_find(
                m,
                settings=app_ctx.settings,
                prompt_template=app_ctx.prompt_template,
                record_call=app_ctx.record_call,
            )

    async def _capture(update, _ctx):
        m = await _whitelisted_command(update, settings.allowed_chat_ids)
        if m: await cmd_capture(m, client=app_ctx.client)

    async def _message(update, _ctx):
        await dispatch(update, app_ctx)

    application.add_handler(CommandHandler("start", _start))
    application.add_handler(CommandHandler("help", _help))
    application.add_handler(CommandHandler("queue", _queue))
    application.add_handler(CommandHandler("last", _last))
    application.add_handler(CommandHandler("find", _find))
    application.add_handler(CommandHandler("capture", _capture))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, _message))
    return application


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    log_event("bot_starting", level=logging.INFO, allowed_chats=len(settings.allowed_chat_ids))
    prompt_template = load_prompt_template(PROMPTS_DIR)

    async def _run() -> None:
        async with CaptureClient(
            base_url=settings.capture_api_base_url,
            token=settings.capture_api_token,
        ) as client:
            app = build_application(settings, client, prompt_template)
            await app.initialize()
            await app.start()
            assert app.updater is not None
            await app.updater.start_polling()
            try:
                await asyncio.Event().wait()
            finally:
                await app.updater.stop()
                await app.stop()
                await app.shutdown()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
