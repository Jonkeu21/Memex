"""Pydantic request/response models for the dashboard backend.

Field names match CLAUDE.md ("Queue item schema", "Retrieval response schema",
"Front-matter conventions", "Rate-limit accounting").
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SourceType = Literal["url", "file", "text", "voice"]
QueueStatus = Literal["queued", "processing", "filed", "needs_review", "failed"]
ClaudeService = Literal["worker", "telegram_bot", "dashboard"]
ClaudePurpose = Literal["file", "retrieve"]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


# ─── Queue ──────────────────────────────────────────────────────────────────

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


class QueueActionAck(BaseModel):
    id: int
    status: QueueStatus


# ─── Inbox triage ───────────────────────────────────────────────────────────

class InboxItem(BaseModel):
    """A file currently sitting in ``_inbox/``."""

    path: str  # vault-relative
    title: str
    captured_at: str | None = None
    processed_at: str | None = None
    confidence: float | None = None
    needs_review: bool = True
    suggested_taxonomy: str | None = None
    reason_for_inbox: str | None = None  # parsed from front-matter (e.g. extraction_failed)
    queue_id: int | None = None
    source: SourceType | None = None
    size_bytes: int | None = None


class InboxListing(BaseModel):
    items: list[InboxItem]


class InboxFile(BaseModel):
    """Full markdown body for the side-panel viewer."""

    path: str
    front_matter: dict[str, Any]
    body: str


class InboxRouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_folder: Annotated[str, Field(min_length=1, max_length=512)]

    @field_validator("target_folder")
    @classmethod
    def _no_dotdot(cls, v: str) -> str:
        if ".." in v.split("/"):
            raise ValueError("target_folder must not contain '..'")
        if v.startswith("/"):
            raise ValueError("target_folder must be vault-relative (no leading /)")
        return v


class InboxRouteAck(BaseModel):
    new_path: str


class InboxDeleteAck(BaseModel):
    trashed_path: str


# ─── Taxonomy ───────────────────────────────────────────────────────────────

class TaxonomyConfidence(BaseModel):
    autonomous_threshold: float = 0.80
    review_threshold: float = 0.60


class TaxonomyOverride(BaseModel):
    autonomous_threshold: float | None = None
    review_threshold: float | None = None


class TaxonomyFolder(BaseModel):
    path: str
    description: str = ""
    keywords: list[str] = []
    confidence_override: TaxonomyOverride | None = None


class TaxonomyDocument(BaseModel):
    schema_version: int = 1
    default_route: str = "_inbox"
    confidence: TaxonomyConfidence = TaxonomyConfidence()
    folders: list[TaxonomyFolder] = []


class TaxonomyResponse(BaseModel):
    document: TaxonomyDocument
    raw_yaml: str


class TaxonomyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document: TaxonomyDocument


# ─── Captures browser ───────────────────────────────────────────────────────

class CaptureFile(BaseModel):
    """A vault note shown in the captures browser."""

    path: str
    title: str
    captured_at: str | None = None
    processed_at: str | None = None
    folder: str
    tags: list[str] = []
    needs_review: bool = False
    size_bytes: int | None = None


class CaptureListing(BaseModel):
    items: list[CaptureFile]
    next_cursor: int | None = None


class CaptureFileBody(BaseModel):
    path: str
    front_matter: dict[str, Any]
    body: str


# ─── Rate-limit ─────────────────────────────────────────────────────────────

class CallsByHourBucket(BaseModel):
    hour: str  # ISO hour bucket, e.g. "2026-05-10T13:00:00Z"
    service: ClaudeService
    count: int
    input_tokens: int
    output_tokens: int


class ClaudeCallRow(BaseModel):
    id: int
    ts: str
    service: ClaudeService
    purpose: ClaudePurpose
    queue_item_id: int | None = None
    session_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    exit_code: int


class RateLimitSnapshot(BaseModel):
    available: bool
    total_24h: int
    error_rate_5m: float
    last_call_ts: str | None = None
    by_hour: list[CallsByHourBucket]
    recent_calls: list[ClaudeCallRow]
    services_breakdown_24h: dict[str, int]


# ─── Retrieval chat ─────────────────────────────────────────────────────────

class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: Annotated[str, Field(min_length=1, max_length=10_000)]

    @field_validator("question")
    @classmethod
    def _strip_check(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question must not be blank")
        return v


class RetrievalSource(BaseModel):
    path: str
    title: str
    exists: bool = True


class RetrievalQuote(BaseModel):
    source_index: int
    text: str


class RetrievalResponse(BaseModel):
    answer: str
    sources: list[RetrievalSource]
    quotes: list[RetrievalQuote]
    confidence: float
    duration_ms: int | None = None
    session_id: str | None = None
