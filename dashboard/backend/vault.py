"""Vault path-safety utilities.

Every vault path that comes from a user-facing request (inbox path params,
captures path params, taxonomy folder targets) must be normalised against the
vault root before any filesystem call happens. Anything that, after
normalisation, is **not** strictly under the vault root is rejected.

This module is the security boundary. It is written defensively; the test
suite exercises a battery of malicious inputs (``..``, absolute paths, NUL
bytes, embedded URL-encoded sequences, Unicode normalisation tricks, symlinks
escaping the vault).
"""
from __future__ import annotations

import os
from pathlib import Path

# Reserved top-level vault folders (per CLAUDE.md "Vault folder structure").
INBOX_DIR_NAME = "_inbox"
META_DIR_NAME = "_meta"
ATTACHMENTS_DIR_NAME = "_attachments"
TRASH_DIR_NAME = "_trash"  # added by the dashboard for inbox "delete" semantics


class VaultPathError(ValueError):
    """Raised when a user-supplied path is unsafe relative to the vault root."""


def _strip_separators(raw: str) -> str:
    """Reject NUL bytes outright; collapse leading slashes."""
    if "\x00" in raw:
        raise VaultPathError("path contains NUL byte")
    return raw.lstrip("/").lstrip("\\")


def safe_join(vault_root: Path, relative: str) -> Path:
    """Resolve ``relative`` against ``vault_root`` and verify it stays inside.

    Does **not** require the target to exist. Returns the resolved absolute
    path. Raises :class:`VaultPathError` for anything that escapes.
    """
    if not isinstance(relative, str):
        raise VaultPathError("path must be a string")
    cleaned = _strip_separators(relative)
    if not cleaned:
        raise VaultPathError("path is empty")
    if any(part == ".." for part in Path(cleaned).parts):
        raise VaultPathError("path contains '..'")
    # Reject Windows drive letters / UNC paths preemptively. Path.resolve()
    # would also catch most of these, but rejecting up front gives a clearer
    # error and prevents any platform-dependent surprises.
    if len(cleaned) >= 2 and cleaned[1] == ":":
        raise VaultPathError("path looks like a Windows drive letter")
    candidate = (vault_root / cleaned).resolve(strict=False)
    root = vault_root.resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise VaultPathError(
            f"path resolves outside the vault root: {candidate}"
        ) from exc
    return candidate


def safe_join_existing(vault_root: Path, relative: str) -> Path:
    """Like :func:`safe_join` but additionally requires the target to exist
    after symlink resolution and to live under the vault root."""
    candidate = safe_join(vault_root, relative)
    if not candidate.exists():
        raise VaultPathError(f"path does not exist: {relative}")
    real = candidate.resolve(strict=True)
    root = vault_root.resolve(strict=False)
    try:
        real.relative_to(root)
    except ValueError as exc:
        raise VaultPathError(
            f"path resolves (via symlink) outside the vault root: {real}"
        ) from exc
    return real


def vault_relative(vault_root: Path, file_path: Path) -> str:
    """Return the vault-relative path string with forward slashes."""
    rel = file_path.relative_to(vault_root.resolve(strict=False))
    return str(rel).replace(os.sep, "/")


def ensure_subdir(vault_root: Path, relative: str) -> Path:
    """``mkdir -p`` a directory under the vault root, returning the path.

    Useful for ensuring ``_trash/<YYYY-MM>/`` exists before moving.
    """
    target = safe_join(vault_root, relative)
    target.mkdir(parents=True, exist_ok=True)
    return target


def is_inbox_path(vault_relative_path: str) -> bool:
    """True if the vault-relative path lives under ``_inbox/``."""
    parts = Path(vault_relative_path).parts
    return bool(parts) and parts[0] == INBOX_DIR_NAME
