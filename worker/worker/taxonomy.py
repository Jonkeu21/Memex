"""Taxonomy loader, validator, and threshold resolver.

Reloaded once per batch (per CLAUDE.md): the worker calls :func:`load` at the
start of every tick, so an operator-edited ``taxonomy.yml`` takes effect on
the next batch with no restart.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = 1
DEFAULT_AUTONOMOUS_THRESHOLD = 0.80
DEFAULT_REVIEW_THRESHOLD = 0.60
DEFAULT_INBOX = "_inbox"

_PATH_RE = re.compile(r"^(?!/)[^\s]+$")


class TaxonomyError(ValueError):
    """Raised when ``taxonomy.yml`` fails validation."""


@dataclass(frozen=True)
class FolderEntry:
    path: str
    description: str
    keywords: tuple[str, ...]
    confidence_override: dict[str, float] | None


@dataclass(frozen=True)
class Taxonomy:
    schema_version: int
    default_route: str
    autonomous_threshold: float
    review_threshold: float
    folders: tuple[FolderEntry, ...]
    raw_yaml: str

    def folder_paths(self) -> list[str]:
        return [f.path for f in self.folders]

    def find_folder(self, path: str) -> FolderEntry | None:
        for f in self.folders:
            if f.path == path:
                return f
        return None

    def resolve_thresholds(self, folder_path: str | None) -> tuple[float, float]:
        if folder_path:
            entry = self.find_folder(folder_path)
            if entry and entry.confidence_override:
                a = float(entry.confidence_override.get("autonomous_threshold", self.autonomous_threshold))
                r = float(entry.confidence_override.get("review_threshold", self.review_threshold))
                return a, r
        return self.autonomous_threshold, self.review_threshold


def _validate_path(path: str) -> None:
    if not isinstance(path, str) or not path:
        raise TaxonomyError(f"folder path must be a non-empty string: {path!r}")
    if path.startswith("/"):
        raise TaxonomyError(f"folder path must not start with '/': {path!r}")
    if ".." in Path(path).parts:
        raise TaxonomyError(f"folder path must not contain '..': {path!r}")
    if not _PATH_RE.match(path):
        raise TaxonomyError(f"folder path must contain no whitespace: {path!r}")


def load(taxonomy_path: Path, vault_dir: Path) -> Taxonomy:
    if not taxonomy_path.exists():
        raise TaxonomyError(f"taxonomy file not found: {taxonomy_path}")
    raw = taxonomy_path.read_text(encoding="utf-8")
    data: Any = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise TaxonomyError("taxonomy.yml root must be a mapping")

    schema_version = data.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise TaxonomyError(
            f"taxonomy schema_version must equal {SCHEMA_VERSION}, got {schema_version!r}"
        )

    default_route = data.get("default_route", DEFAULT_INBOX)
    if not isinstance(default_route, str) or not default_route:
        raise TaxonomyError("default_route must be a non-empty string")

    confidence = data.get("confidence") or {}
    autonomous = float(confidence.get("autonomous_threshold", DEFAULT_AUTONOMOUS_THRESHOLD))
    review = float(confidence.get("review_threshold", DEFAULT_REVIEW_THRESHOLD))
    if not (0.0 <= review <= autonomous <= 1.0):
        raise TaxonomyError(
            f"thresholds must satisfy 0<=review<=autonomous<=1, got review={review} autonomous={autonomous}"
        )

    raw_folders = data.get("folders") or []
    if not isinstance(raw_folders, list):
        raise TaxonomyError("folders must be a list")

    folders: list[FolderEntry] = []
    seen_paths: set[str] = set()
    for entry in raw_folders:
        if not isinstance(entry, dict):
            raise TaxonomyError(f"folder entry must be a mapping, got {entry!r}")
        path = entry.get("path")
        _validate_path(path)
        if path in seen_paths:
            raise TaxonomyError(f"duplicate folder path: {path!r}")
        seen_paths.add(path)
        keywords_raw = entry.get("keywords") or []
        if not isinstance(keywords_raw, list):
            raise TaxonomyError(f"keywords must be a list for folder {path!r}")
        override = entry.get("confidence_override")
        if override is not None and not isinstance(override, dict):
            raise TaxonomyError(f"confidence_override must be a mapping for folder {path!r}")
        if isinstance(override, dict):
            a = float(override.get("autonomous_threshold", autonomous))
            r = float(override.get("review_threshold", review))
            if not (0.0 <= r <= a <= 1.0):
                raise TaxonomyError(f"confidence_override invalid for {path!r}: review={r} autonomous={a}")
        folders.append(
            FolderEntry(
                path=path,
                description=str(entry.get("description") or ""),
                keywords=tuple(str(k) for k in keywords_raw),
                confidence_override=dict(override) if isinstance(override, dict) else None,
            )
        )

    default_dir = vault_dir / default_route
    if not default_dir.is_dir():
        raise TaxonomyError(f"default_route directory does not exist under vault: {default_dir}")

    return Taxonomy(
        schema_version=schema_version,
        default_route=default_route,
        autonomous_threshold=autonomous,
        review_threshold=review,
        folders=tuple(folders),
        raw_yaml=raw,
    )
