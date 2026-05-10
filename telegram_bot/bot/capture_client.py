"""Async HTTP client for the capture API.

Wraps the four POST endpoints (`/captures/url`, `/captures/text`,
`/captures/file`, `/captures/voice`) plus a GET helper used by `/queue` and
`/last`. Every call carries the bearer token. Errors are surfaced as
``CaptureAPIError`` so handlers can render a uniform user-facing message
without inspecting HTTP status codes themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class CaptureAPIError(RuntimeError):
    """Raised on any non-2xx response or transport-level failure."""

    def __init__(self, message: str, *, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


@dataclass
class CaptureAck:
    id: int
    status: str
    created_at: str


def _ack_from_payload(payload: Any) -> CaptureAck:
    if not isinstance(payload, dict):
        raise CaptureAPIError("capture API returned non-object body")
    try:
        return CaptureAck(
            id=int(payload["id"]),
            status=str(payload["status"]),
            created_at=str(payload["created_at"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CaptureAPIError(f"capture API ack payload malformed: {exc}") from exc


class CaptureClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "CaptureClient":
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()

    async def _post_json(self, path: str, payload: dict[str, Any]) -> CaptureAck:
        try:
            resp = await self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise CaptureAPIError(f"transport error: {exc}") from exc
        if resp.status_code not in (200, 202):
            raise CaptureAPIError(
                f"capture API {path} returned {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text[:500],
            )
        return _ack_from_payload(resp.json())

    async def _post_multipart(
        self, path: str, *, filename: str, content: bytes, content_type: str
    ) -> CaptureAck:
        files = {"file": (filename, content, content_type)}
        try:
            resp = await self._client.post(path, files=files)
        except httpx.HTTPError as exc:
            raise CaptureAPIError(f"transport error: {exc}") from exc
        if resp.status_code not in (200, 202):
            raise CaptureAPIError(
                f"capture API {path} returned {resp.status_code}",
                status_code=resp.status_code,
                body=resp.text[:500],
            )
        return _ack_from_payload(resp.json())

    async def capture_url(self, url: str, user_note: str | None = None) -> CaptureAck:
        payload: dict[str, Any] = {"url": url}
        if user_note:
            payload["user_note"] = user_note
        return await self._post_json("/captures/url", payload)

    async def capture_text(self, text: str) -> CaptureAck:
        return await self._post_json("/captures/text", {"text": text})

    async def capture_file(self, *, filename: str, content: bytes, content_type: str) -> CaptureAck:
        return await self._post_multipart(
            "/captures/file",
            filename=filename,
            content=content,
            content_type=content_type,
        )

    async def capture_voice(self, *, filename: str, content: bytes, content_type: str) -> CaptureAck:
        return await self._post_multipart(
            "/captures/voice",
            filename=filename,
            content=content,
            content_type=content_type,
        )
