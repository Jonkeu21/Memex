"""Recent vault captures browser.

Walks the vault's PARA folders + ``_inbox/`` for ``.md`` files and surfaces
their front-matter to the frontend table. The viewer panel is served by
``GET /api/v1/captures/{path}`` which returns the parsed markdown body.

This endpoint is read-only and does **not** require the bearer token —
walking the vault is harmless and the tailnet is the trust boundary.
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path as PathParam, Query, Request, status

from ..frontmatter import parse_file
from ..logging import log_event
from ..schemas import CaptureFile, CaptureFileBody, CaptureListing
from ..vault import (
    INBOX_DIR_NAME,
    VaultPathError,
    safe_join_existing,
    vault_relative,
)

router = APIRouter(prefix="/api/v1/captures", tags=["captures"])

# Folders the captures browser walks. ``_meta``/``_attachments``/``_trash`` are
# intentionally excluded — they aren't notes the operator wants to triage.
_BROWSED_FOLDERS = (
    "projects",
    "areas",
    "resources",
    "archive",
    INBOX_DIR_NAME,
)


def _walk_vault(vault_dir: Path) -> list[Path]:
    out: list[Path] = []
    for folder_name in _BROWSED_FOLDERS:
        root = vault_dir / folder_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue
            out.append(path)
    return out


def _row_for(vault_dir: Path, path: Path) -> CaptureFile | None:
    try:
        parsed = parse_file(path)
    except (OSError, UnicodeDecodeError):
        return None
    fm = parsed.front_matter
    rel = vault_relative(vault_dir, path)
    folder = "/".join(Path(rel).parts[:-1]) or rel
    title = fm.get("title")
    if not title:
        # Fall back to the filename minus the YYYY-MM-DD-- prefix.
        stem = path.stem
        if "--" in stem:
            _, _, after = stem.partition("--")
            title = after.replace("-", " ").strip() if after else stem
        else:
            title = stem.replace("-", " ").strip() or "Untitled"
    tags = fm.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    return CaptureFile(
        path=rel,
        title=str(title),
        captured_at=str(fm["captured_at"]) if "captured_at" in fm else None,
        processed_at=str(fm["processed_at"]) if "processed_at" in fm else None,
        folder=folder,
        tags=[str(t) for t in tags],
        needs_review=bool(fm.get("needs_review", False)),
        size_bytes=path.stat().st_size,
    )


@router.get("", response_model=CaptureListing)
def list_captures(
    request: Request,
    folder: Annotated[str | None, Query(description="Filter by exact folder prefix.")] = None,
    q: Annotated[str | None, Query(description="Free-text search over titles/tags.")] = None,
    needs_review: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    cursor: Annotated[int | None, Query(ge=0)] = None,
) -> CaptureListing:
    settings = request.app.state.settings
    vault = settings.vault_dir
    rows: list[CaptureFile] = []
    for path in _walk_vault(vault):
        row = _row_for(vault, path)
        if row is None:
            continue
        if folder and not row.path.startswith(folder.rstrip("/") + "/"):
            continue
        if needs_review is not None and row.needs_review != needs_review:
            continue
        if q:
            needle = q.lower()
            haystack = " ".join([row.title.lower(), row.path.lower(), " ".join(t.lower() for t in row.tags)])
            if needle not in haystack:
                continue
        rows.append(row)

    # Sort newest first by captured_at, falling back to processed_at then path.
    def sort_key(c: CaptureFile) -> tuple[Any, ...]:
        return (
            c.captured_at or "",
            c.processed_at or "",
            c.path,
        )

    rows.sort(key=sort_key, reverse=True)
    start = cursor or 0
    paged = rows[start : start + limit + 1]
    next_cursor: int | None = None
    if len(paged) > limit:
        paged = paged[:limit]
        next_cursor = start + limit
    return CaptureListing(items=paged, next_cursor=next_cursor)


@router.get("/{path:path}", response_model=CaptureFileBody)
def get_capture_body(
    path: Annotated[str, PathParam(min_length=1, max_length=512)],
    request: Request,
) -> CaptureFileBody:
    vault = request.app.state.settings.vault_dir
    try:
        absolute = safe_join_existing(vault, path)
    except VaultPathError as exc:
        log_event("capture_path_rejected", level=30, path=path, reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_path", "message": str(exc)}},
        )
    if not absolute.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": f"no capture at {path}"}},
        )
    if absolute.suffix != ".md":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "not_a_note",
                    "message": "captures viewer only handles markdown files",
                }
            },
        )
    parsed = parse_file(absolute)
    rel = vault_relative(vault, absolute)
    return CaptureFileBody(path=rel, front_matter=parsed.front_matter, body=parsed.body)
