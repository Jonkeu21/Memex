"""``_inbox/`` triage: list, view, route to a taxonomy folder, trash."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Request, status

from ..auth import require_token
from ..frontmatter import parse_file, patch_field
from ..logging import log_event
from ..schemas import (
    InboxDeleteAck,
    InboxFile,
    InboxItem,
    InboxListing,
    InboxRouteAck,
    InboxRouteRequest,
)
from ..taxonomy_io import TaxonomyError, load_from_disk
from ..vault import (
    INBOX_DIR_NAME,
    TRASH_DIR_NAME,
    VaultPathError,
    ensure_subdir,
    safe_join,
    safe_join_existing,
    vault_relative,
)

router = APIRouter(prefix="/api/v1/inbox", tags=["inbox"])

# Path param uses a free-form string with internal slashes. The {path:path}
# converter accepts everything after the prefix, so URL-encoded "../" segments
# arrive intact and are caught by the safe_join check below.
_PATH_PARAM = PathParam(min_length=1, max_length=512)


def _vault_dir(request: Request) -> Path:
    return request.app.state.settings.vault_dir


def _summarise(rel_path: str, parsed_front_matter: dict[str, Any], size: int) -> InboxItem:
    """Build an :class:`InboxItem` from a parsed note's front-matter."""
    fm = parsed_front_matter
    title = (
        fm.get("title")
        or _title_from_filename(rel_path)
    )
    suggested = None
    reason = None
    # Some inbox files were placed there because extraction failed — surface that.
    if fm.get("extraction_failed"):
        reason = "extraction failed"
    if fm.get("taxonomy_path") and fm.get("taxonomy_path") != INBOX_DIR_NAME:
        suggested = fm.get("taxonomy_path")
    return InboxItem(
        path=rel_path,
        title=str(title),
        captured_at=str(fm["captured_at"]) if "captured_at" in fm else None,
        processed_at=str(fm["processed_at"]) if "processed_at" in fm else None,
        confidence=float(fm["confidence"]) if isinstance(fm.get("confidence"), (int, float)) else None,
        needs_review=bool(fm.get("needs_review", True)),
        suggested_taxonomy=suggested,
        reason_for_inbox=reason,
        queue_id=int(fm["id"]) if isinstance(fm.get("id"), int) else None,
        source=fm.get("source") if fm.get("source") in {"url", "file", "text", "voice"} else None,
        size_bytes=size,
    )


def _title_from_filename(rel_path: str) -> str:
    name = Path(rel_path).stem
    if "--" in name:
        # Default filename shape is YYYY-MM-DD--<slug>.
        _, _, after = name.partition("--")
        if after:
            name = after
    return name.replace("-", " ").strip() or "Untitled"


@router.get("", response_model=InboxListing)
def list_inbox(request: Request) -> InboxListing:
    vault = _vault_dir(request)
    inbox_dir = vault / INBOX_DIR_NAME
    items: list[InboxItem] = []
    if not inbox_dir.is_dir():
        return InboxListing(items=items)
    # Sort newest first (mtime desc), excluding hidden/system files.
    candidates = sorted(
        (p for p in inbox_dir.iterdir() if p.is_file() and p.suffix == ".md" and not p.name.startswith(".")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            parsed = parse_file(path)
        except (OSError, UnicodeDecodeError):
            continue
        rel = vault_relative(vault, path)
        items.append(_summarise(rel, parsed.front_matter, path.stat().st_size))
    return InboxListing(items=items)


@router.get("/{path:path}", response_model=InboxFile)
def get_inbox_file(
    path: Annotated[str, _PATH_PARAM],
    request: Request,
) -> InboxFile:
    vault = _vault_dir(request)
    try:
        absolute = safe_join_existing(vault, path)
    except VaultPathError as exc:
        log_event("inbox_path_rejected", level=30, path=path, reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_path", "message": str(exc)}},
        )
    rel = vault_relative(vault, absolute)
    if not rel.startswith(INBOX_DIR_NAME + "/") and rel != INBOX_DIR_NAME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "not_in_inbox",
                    "message": f"path is not under {INBOX_DIR_NAME}/",
                }
            },
        )
    if not absolute.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": f"no inbox file at {rel}"}},
        )
    parsed = parse_file(absolute)
    return InboxFile(path=rel, front_matter=parsed.front_matter, body=parsed.body)


@router.post(
    "/{path:path}/route",
    response_model=InboxRouteAck,
    dependencies=[Depends(require_token)],
)
def route_inbox_file(
    path: Annotated[str, _PATH_PARAM],
    payload: InboxRouteRequest,
    request: Request,
) -> InboxRouteAck:
    vault = _vault_dir(request)
    try:
        source = safe_join_existing(vault, path)
    except VaultPathError as exc:
        log_event("inbox_path_rejected", level=30, path=path, reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_path", "message": str(exc)}},
        )
    if vault_relative(vault, source).split("/")[0] != INBOX_DIR_NAME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "not_in_inbox",
                    "message": f"source must live under {INBOX_DIR_NAME}/",
                }
            },
        )

    # Validate the target folder lives in taxonomy.yml and is safe.
    target_folder_rel = payload.target_folder.rstrip("/")
    try:
        target_dir = safe_join(vault, target_folder_rel)
    except VaultPathError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_path", "message": str(exc)}},
        )
    if target_folder_rel.split("/")[0] in {INBOX_DIR_NAME, TRASH_DIR_NAME}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "invalid_target",
                    "message": f"cannot route into {target_folder_rel} from inbox",
                }
            },
        )
    settings = request.app.state.settings
    taxonomy_path = settings.vault_dir / "_meta" / "taxonomy.yml"
    try:
        loaded = load_from_disk(taxonomy_path)
    except TaxonomyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "taxonomy_invalid", "message": str(exc)}},
        )
    folder_paths = {f.path for f in loaded.document.folders}
    if target_folder_rel not in folder_paths:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "unknown_folder",
                    "message": (
                        f"target_folder {target_folder_rel!r} is not declared in "
                        "taxonomy.yml"
                    ),
                }
            },
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    new_path = target_dir / source.name
    if new_path.exists():
        # Disambiguate to YYYY-MM-DD--<slug>-N.md
        stem = source.stem
        n = 2
        while True:
            candidate = target_dir / f"{stem}-{n}.md"
            if not candidate.exists():
                new_path = candidate
                break
            n += 1

    # Patch front-matter to clear needs_review and update taxonomy_path. We
    # re-write the source file first (atomic), then rename the file. If
    # anything fails between these steps, the source still exists and the
    # caller can retry.
    try:
        original_text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "io_error", "message": f"could not read source: {exc}"}},
        )
    try:
        patched = patch_field(original_text, "needs_review", False)
        patched = patch_field(patched, "taxonomy_path", target_folder_rel)
    except ValueError:
        # No front-matter to patch — leave the body untouched but still move.
        patched = original_text

    tmp = source.with_suffix(source.suffix + ".routing.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(patched.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    os.replace(tmp, source)
    os.replace(source, new_path)

    rel_new = vault_relative(vault, new_path)
    log_event(
        "inbox_routed",
        from_path=path,
        to_path=rel_new,
        target_folder=target_folder_rel,
    )
    return InboxRouteAck(new_path=rel_new)


@router.post(
    "/{path:path}/delete",
    response_model=InboxDeleteAck,
    dependencies=[Depends(require_token)],
)
def delete_inbox_file(
    path: Annotated[str, _PATH_PARAM],
    request: Request,
) -> InboxDeleteAck:
    """Move an inbox file to ``_trash/<YYYY-MM>/<filename>``.

    The vault holds the operator's irreplaceable knowledge — we never call
    ``unlink`` on inbox content. The trash is monthly so the folder doesn't
    grow unboundedly while still being easy to inspect.
    """
    vault = _vault_dir(request)
    try:
        source = safe_join_existing(vault, path)
    except VaultPathError as exc:
        log_event("inbox_path_rejected", level=30, path=path, reason=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "invalid_path", "message": str(exc)}},
        )
    rel = vault_relative(vault, source)
    if rel.split("/")[0] != INBOX_DIR_NAME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "not_in_inbox",
                    "message": f"source must live under {INBOX_DIR_NAME}/",
                }
            },
        )
    bucket = datetime.now(timezone.utc).strftime("%Y-%m")
    trash_dir = ensure_subdir(vault, f"{TRASH_DIR_NAME}/{bucket}")
    target = trash_dir / source.name
    n = 2
    while target.exists():
        target = trash_dir / f"{source.stem}-{n}{source.suffix}"
        n += 1
    os.replace(source, target)
    rel_trashed = vault_relative(vault, target)
    log_event("inbox_trashed", from_path=path, to_path=rel_trashed)
    return InboxDeleteAck(trashed_path=rel_trashed)
