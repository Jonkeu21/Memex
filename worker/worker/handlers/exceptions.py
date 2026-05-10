"""Typed exceptions raised by source-type handlers."""
from __future__ import annotations


class HandlerError(Exception):
    """Base for handler-side failures."""


class TransientHandlerError(HandlerError):
    """Retryable: network blip, subprocess crash. Worker re-queues the row."""


class PermanentHandlerError(HandlerError):
    """Non-retryable extraction failure. Worker writes an _inbox stub note."""
