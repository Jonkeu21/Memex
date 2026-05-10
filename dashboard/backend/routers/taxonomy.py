"""Taxonomy CRUD: read the parsed YAML, save edits atomically."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..auth import require_token
from ..logging import log_event
from ..schemas import TaxonomyResponse, TaxonomyUpdateRequest
from ..taxonomy_io import (
    TaxonomyError,
    load_from_disk,
    save_to_disk,
)

router = APIRouter(prefix="/api/v1/taxonomy", tags=["taxonomy"])


def _taxonomy_path(request: Request) -> Path:
    settings = request.app.state.settings
    return settings.vault_dir / "_meta" / "taxonomy.yml"


@router.get("", response_model=TaxonomyResponse)
def get_taxonomy(request: Request) -> TaxonomyResponse:
    path = _taxonomy_path(request)
    try:
        loaded = load_from_disk(path)
    except TaxonomyError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "taxonomy_invalid", "message": str(exc)}},
        )
    return TaxonomyResponse(document=loaded.document, raw_yaml=loaded.raw_yaml)


@router.put(
    "",
    response_model=TaxonomyResponse,
    dependencies=[Depends(require_token)],
)
def put_taxonomy(payload: TaxonomyUpdateRequest, request: Request) -> TaxonomyResponse:
    path = _taxonomy_path(request)
    try:
        rendered = save_to_disk(path, payload.document)
    except TaxonomyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "taxonomy_invalid", "message": str(exc)}},
        )
    log_event(
        "taxonomy_saved",
        folder_count=len(payload.document.folders),
    )
    return TaxonomyResponse(document=payload.document, raw_yaml=rendered)
