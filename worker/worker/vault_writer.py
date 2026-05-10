"""Atomic vault note writer.

Responsible for slugging titles, building filenames (with collision suffixes),
producing front-matter in the strict CLAUDE.md field order, and writing notes
durably (write-temp, fsync, rename, fsync directory).
"""
from __future__ import annotations

import io
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import date as date_cls
from pathlib import Path
from typing import Any

SLUG_MAX_LEN = 60
_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_DASH_RUN = re.compile(r"-{2,}")


class VaultWriteCrash(RuntimeError):
    """Test seam: raised after the temp file is written but before rename."""


def slugify(title: str) -> str:
    if not title:
        return "untitled"
    norm = unicodedata.normalize("NFKD", title)
    ascii_only = norm.encode("ascii", "ignore").decode("ascii")
    lower = ascii_only.lower()
    kebab = _SLUG_NON_ALNUM.sub("-", lower)
    kebab = _DASH_RUN.sub("-", kebab).strip("-")
    if not kebab:
        return "untitled"
    if len(kebab) > SLUG_MAX_LEN:
        kebab = kebab[:SLUG_MAX_LEN].rstrip("-") or "untitled"
    return kebab


def build_filename(target_dir: Path, captured_date: date_cls, slug: str) -> Path:
    """Return a non-colliding ``YYYY-MM-DD--<slug>[-N].md`` path under ``target_dir``."""
    base = f"{captured_date.isoformat()}--{slug}"
    candidate = target_dir / f"{base}.md"
    n = 2
    while candidate.exists():
        candidate = target_dir / f"{base}-{n}.md"
        n += 1
    return candidate


def atomic_write(
    path: Path,
    content: str,
    *,
    crash_after_temp: bool = False,
) -> None:
    """Write ``content`` to ``path`` atomically.

    The flow is: write to ``path + ".tmp"``, fsync the temp file, ``rename``
    to the target, fsync the parent directory. ``crash_after_temp`` is a test
    seam — when true, the temp file is created and fsynced but the rename is
    skipped and :class:`VaultWriteCrash` is raised. The caller's recovery is
    expected to clean up by removing any leftover ``.tmp`` files.
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
    if crash_after_temp:
        raise VaultWriteCrash("crash_after_temp set — leaving .tmp without rename")
    os.replace(tmp, path)
    try:
        dfd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass


def _normalize_tags(tags: list[str] | tuple[str, ...] | None) -> list[str]:
    if not tags:
        return []
    out: set[str] = set()
    for t in tags:
        if not isinstance(t, str):
            continue
        s = slugify(t)
        if s and s != "untitled":
            out.add(s)
    return sorted(out)


_YAML_RESERVED_FIRST = ("- ", "? ", "! ", "@ ", "& ", "* ", "% ", "> ", "| ", "{", "}", "[", "]", ",", "#", "`")
_YAML_RESERVED_VALUES = {"null", "Null", "NULL", "true", "True", "TRUE", "false", "False", "FALSE",
                         "yes", "Yes", "YES", "no", "No", "NO", "on", "On", "ON", "off", "Off", "OFF", "~"}


def _needs_quoting(s: str) -> bool:
    if s == "":
        return True
    if s.strip() != s:
        return True
    if s in _YAML_RESERVED_VALUES:
        return True
    if s.startswith(_YAML_RESERVED_FIRST):
        return True
    if "\n" in s or "\"" in s or "'" in s:
        return True
    if ": " in s or s.endswith(":"):
        return True
    if " #" in s:
        return True
    return False


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    if _needs_quoting(s):
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return s


def _yaml_tag_list(tags: list[str]) -> str:
    if not tags:
        return "[]"
    return "[" + ", ".join(_yaml_scalar(t) for t in tags) + "]"


@dataclass(frozen=True)
class FrontMatter:
    id: int
    source: str
    captured_at: str
    processed_at: str
    confidence: float
    taxonomy_path: str
    tags: list[str]
    needs_review: bool
    original_url: str | None = None
    attachment: str | None = None

    def render(self) -> str:
        out = io.StringIO()
        out.write("---\n")
        out.write(f"id: {self.id}\n")
        out.write(f"source: {_yaml_scalar(self.source)}\n")
        out.write(f"captured_at: {_yaml_scalar(self.captured_at)}\n")
        out.write(f"processed_at: {_yaml_scalar(self.processed_at)}\n")
        out.write(f"confidence: {self.confidence}\n")
        out.write(f"taxonomy_path: {_yaml_scalar(self.taxonomy_path)}\n")
        out.write(f"tags: {_yaml_tag_list(self.tags)}\n")
        out.write(f"needs_review: {'true' if self.needs_review else 'false'}\n")
        if self.source == "url" and self.original_url is not None:
            out.write(f"original_url: {_yaml_scalar(self.original_url)}\n")
        if self.source in {"file", "voice"} and self.attachment is not None:
            out.write(f"attachment: {_yaml_scalar(self.attachment)}\n")
        out.write("---\n")
        return out.getvalue()


def build_front_matter(
    *,
    queue_id: int,
    source: str,
    captured_at: str,
    processed_at: str,
    confidence: float,
    taxonomy_path: str,
    tags: list[str] | None,
    needs_review: bool,
    original_url: str | None = None,
    attachment: str | None = None,
) -> FrontMatter:
    return FrontMatter(
        id=int(queue_id),
        source=source,
        captured_at=captured_at,
        processed_at=processed_at,
        confidence=float(confidence),
        taxonomy_path=taxonomy_path,
        tags=_normalize_tags(tags),
        needs_review=bool(needs_review),
        original_url=original_url,
        attachment=attachment,
    )


def render_note(
    *,
    front_matter: FrontMatter,
    title: str,
    summary: str,
    body_content: str,
) -> str:
    parts = [front_matter.render()]
    parts.append(f"\n# {title.strip() or 'Untitled'}\n")
    parts.append("\n")
    parts.append(summary.strip() + "\n" if summary else "\n")
    parts.append("\n## Source\n\n")
    parts.append(body_content if body_content.endswith("\n") else body_content + "\n")
    return "".join(parts)


def vault_relative(vault_dir: Path, file_path: Path) -> str:
    return str(file_path.relative_to(vault_dir)).replace(os.sep, "/")


def write_note(
    *,
    vault_dir: Path,
    target_folder: str,
    captured_date: date_cls,
    title: str,
    summary: str,
    body_content: str,
    front_matter: FrontMatter,
    crash_after_temp: bool = False,
) -> str:
    """Write a note and return the vault-relative path."""
    folder = vault_dir / target_folder
    folder.mkdir(parents=True, exist_ok=True)
    slug = slugify(title)
    file_path = build_filename(folder, captured_date, slug)
    content = render_note(
        front_matter=front_matter,
        title=title,
        summary=summary,
        body_content=body_content,
    )
    atomic_write(file_path, content, crash_after_temp=crash_after_temp)
    return vault_relative(vault_dir, file_path)
