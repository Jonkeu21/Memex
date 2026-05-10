"""Request and response models. Field names match CLAUDE.md."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

SourceType = Literal["url", "file", "text", "voice"]
QueueStatus = Literal["queued", "processing", "filed", "needs_review", "failed"]


class UrlCapture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: HttpUrl
    user_note: Annotated[str, Field(default="", max_length=2000)] = ""


class TextCapture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Annotated[str, Field(min_length=1, max_length=100_000)]

    @field_validator("text")
    @classmethod
    def _strip_check(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be blank")
        return v


class CaptureAck(BaseModel):
    id: int
    status: QueueStatus
    created_at: str


class ErrorEnvelope(BaseModel):
    code: str
    message: str


class QueueItem(BaseModel):
    id: int
    created_at: str
    updated_at: str
    source_type: SourceType
    source_payload: dict[str, Any]
    submitter: str
    status: QueueStatus
    attempts: int
    last_error: str | None = None
    processed_at: str | None = None
    confidence: float | None = None
    vault_path: str | None = None
    claude_session_id: str | None = None
    claude_input_tokens: int | None = None
    claude_output_tokens: int | None = None
    claude_duration_ms: int | None = None


class QueueListing(BaseModel):
    items: list[QueueItem]
    next_cursor: int | None = None
