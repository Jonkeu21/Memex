"""Read / parse / validate / write ``vault/_meta/taxonomy.yml``.

The dashboard's taxonomy editor is the canonical UI for this file. The worker
re-reads it on every batch tick (per CLAUDE.md), so a successful save here is
picked up within ~5–60 seconds without restarting the worker.

Validation rules mirror :mod:`worker.worker.taxonomy` so the worker doesn't
reject the file the dashboard just wrote. Where the rules differ, that is a
contract bug — fix the contract, not the validator.
"""
from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import schemas as S

SCHEMA_VERSION = 1
DEFAULT_AUTONOMOUS_THRESHOLD = 0.80
DEFAULT_REVIEW_THRESHOLD = 0.60
DEFAULT_INBOX = "_inbox"
MAX_FOLDER_DEPTH = 6  # sane upper bound; vault navigation gets unwieldy past this

_PATH_RE = re.compile(r"^(?!/)[^\s]+$")
_FILESYSTEM_SAFE_RE = re.compile(r"^[A-Za-z0-9._\-/]+$")


class TaxonomyError(ValueError):
    """Raised when ``taxonomy.yml`` fails validation."""


@dataclass(frozen=True)
class LoadedTaxonomy:
    document: S.TaxonomyDocument
    raw_yaml: str


def _validate_path(path: Any) -> str:
    if not isinstance(path, str) or not path:
        raise TaxonomyError(f"folder path must be a non-empty string: {path!r}")
    if path.startswith("/"):
        raise TaxonomyError(f"folder path must not start with '/': {path!r}")
    if ".." in Path(path).parts:
        raise TaxonomyError(f"folder path must not contain '..': {path!r}")
    if not _PATH_RE.match(path):
        raise TaxonomyError(f"folder path must contain no whitespace: {path!r}")
    if not _FILESYSTEM_SAFE_RE.match(path):
        raise TaxonomyError(
            f"folder path contains filesystem-unsafe characters: {path!r}"
        )
    parts = Path(path).parts
    if len(parts) > MAX_FOLDER_DEPTH:
        raise TaxonomyError(
            f"folder path depth {len(parts)} exceeds max {MAX_FOLDER_DEPTH}: {path!r}"
        )
    for part in parts:
        if part in {".", ""}:
            raise TaxonomyError(f"folder path has empty/dot segment: {path!r}")
    return path


def _validate_thresholds(autonomous: float, review: float, *, where: str = "global") -> None:
    if not (0.0 <= review <= autonomous <= 1.0):
        raise TaxonomyError(
            f"thresholds must satisfy 0<=review<=autonomous<=1 ({where}); "
            f"got review={review} autonomous={autonomous}"
        )


def parse(raw: str) -> LoadedTaxonomy:
    """Parse a YAML document into the typed :class:`LoadedTaxonomy`.

    Validation is strict enough that anything which passes here will also
    pass the worker's loader.
    """
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise TaxonomyError(f"taxonomy.yml is not valid YAML: {exc}") from exc

    if data is None:
        # An empty file is treated as "default doc" rather than an error.
        data = {}
    if not isinstance(data, dict):
        raise TaxonomyError("taxonomy.yml root must be a mapping")

    schema_version = data.get("schema_version", SCHEMA_VERSION)
    if schema_version != SCHEMA_VERSION:
        raise TaxonomyError(
            f"schema_version must equal {SCHEMA_VERSION}, got {schema_version!r}"
        )

    default_route = data.get("default_route", DEFAULT_INBOX)
    if not isinstance(default_route, str) or not default_route:
        raise TaxonomyError("default_route must be a non-empty string")

    confidence_block = data.get("confidence") or {}
    if not isinstance(confidence_block, dict):
        raise TaxonomyError("confidence must be a mapping")
    autonomous = float(confidence_block.get("autonomous_threshold", DEFAULT_AUTONOMOUS_THRESHOLD))
    review = float(confidence_block.get("review_threshold", DEFAULT_REVIEW_THRESHOLD))
    _validate_thresholds(autonomous, review)

    raw_folders = data.get("folders") or []
    if not isinstance(raw_folders, list):
        raise TaxonomyError("folders must be a list")

    folders: list[S.TaxonomyFolder] = []
    seen_paths: set[str] = set()
    for entry in raw_folders:
        if not isinstance(entry, dict):
            raise TaxonomyError(f"folder entry must be a mapping, got {entry!r}")
        path = _validate_path(entry.get("path"))
        if path in seen_paths:
            raise TaxonomyError(f"duplicate folder path: {path!r}")
        seen_paths.add(path)
        keywords_raw = entry.get("keywords") or []
        if not isinstance(keywords_raw, list):
            raise TaxonomyError(f"keywords must be a list for folder {path!r}")
        keywords = [str(k) for k in keywords_raw]

        override_raw = entry.get("confidence_override")
        override: S.TaxonomyOverride | None
        if override_raw is None:
            override = None
        elif isinstance(override_raw, dict):
            a = override_raw.get("autonomous_threshold")
            r = override_raw.get("review_threshold")
            af = float(a) if a is not None else autonomous
            rf = float(r) if r is not None else review
            _validate_thresholds(af, rf, where=f"folder {path!r}")
            override = S.TaxonomyOverride(
                autonomous_threshold=float(a) if a is not None else None,
                review_threshold=float(r) if r is not None else None,
            )
        else:
            raise TaxonomyError(
                f"confidence_override must be a mapping for folder {path!r}"
            )

        folders.append(
            S.TaxonomyFolder(
                path=path,
                description=str(entry.get("description") or ""),
                keywords=keywords,
                confidence_override=override,
            )
        )

    document = S.TaxonomyDocument(
        schema_version=schema_version,
        default_route=default_route,
        confidence=S.TaxonomyConfidence(
            autonomous_threshold=autonomous,
            review_threshold=review,
        ),
        folders=folders,
    )
    return LoadedTaxonomy(document=document, raw_yaml=raw)


def render(document: S.TaxonomyDocument) -> str:
    """Render a typed taxonomy document back to YAML.

    Output is deterministic and matches the shape shown in CLAUDE.md so the
    file stays diffable when round-tripped through the dashboard editor.
    """
    out = io.StringIO()
    out.write(f"schema_version: {int(document.schema_version)}\n")
    out.write(f"default_route: {_yaml_scalar(document.default_route)}\n")
    out.write("confidence:\n")
    out.write(f"  autonomous_threshold: {document.confidence.autonomous_threshold}\n")
    out.write(f"  review_threshold: {document.confidence.review_threshold}\n")
    out.write("folders:\n")
    if not document.folders:
        return out.getvalue()
    for folder in document.folders:
        out.write(f"  - path: {_yaml_scalar(folder.path)}\n")
        out.write(f"    description: {_yaml_scalar(folder.description)}\n")
        if folder.keywords:
            kws = ", ".join(_yaml_scalar(k) for k in folder.keywords)
            out.write(f"    keywords: [{kws}]\n")
        else:
            out.write("    keywords: []\n")
        if folder.confidence_override is None:
            out.write("    confidence_override: null\n")
        else:
            out.write("    confidence_override:\n")
            o = folder.confidence_override
            if o.autonomous_threshold is not None:
                out.write(f"      autonomous_threshold: {o.autonomous_threshold}\n")
            if o.review_threshold is not None:
                out.write(f"      review_threshold: {o.review_threshold}\n")
            if o.autonomous_threshold is None and o.review_threshold is None:
                out.write("      {}\n")
    return out.getvalue()


_YAML_RESERVED = {
    "null", "Null", "NULL", "true", "True", "TRUE", "false", "False", "FALSE",
    "yes", "Yes", "YES", "no", "No", "NO", "on", "On", "ON", "off", "Off", "OFF", "~",
}


def _yaml_scalar(value: str) -> str:
    if value == "":
        return '""'
    if value in _YAML_RESERVED:
        return f'"{value}"'
    if any(ch in value for ch in (":", "#", "\n", "\"", "'", "[", "]", "{", "}", ",", "&", "*", "?", "|", ">", "%", "@", "`")):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if value != value.strip():
        return f'"{value}"'
    return value


def load_from_disk(path: Path) -> LoadedTaxonomy:
    if not path.exists():
        # Synthesise a default doc so the dashboard can show something useful
        # before the operator has authored a real taxonomy.
        return LoadedTaxonomy(
            document=S.TaxonomyDocument(),
            raw_yaml="",
        )
    raw = path.read_text(encoding="utf-8")
    return parse(raw)


def atomic_write(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically with fsync.

    Mirrors :func:`worker.worker.vault_writer.atomic_write` semantics.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = content.encode("utf-8")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    os.replace(tmp, path)
    try:
        dfd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass


def save_to_disk(path: Path, document: S.TaxonomyDocument) -> str:
    """Validate, render, and atomically write a taxonomy document to disk.

    Returns the rendered YAML so the caller can echo it in the response.
    """
    # Round-trip through ``parse`` so any constraint that the typed model
    # didn't enforce (path uniqueness, depth, threshold ordering) still
    # rejects bad input *before* we touch disk.
    rendered = render(document)
    parse(rendered)
    atomic_write(path, rendered)
    return rendered
