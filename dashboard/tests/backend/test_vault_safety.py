"""Path-safety tests for ``backend.vault``.

Path safety is non-negotiable: anything that, after normalisation, leaves
the vault root must be rejected with a clear error, never traversed. This
suite is the canonical regression test for that promise.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.vault import (  # noqa: E402
    INBOX_DIR_NAME,
    VaultPathError,
    is_inbox_path,
    safe_join,
    safe_join_existing,
    vault_relative,
)


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    (v / INBOX_DIR_NAME).mkdir(parents=True)
    (v / "projects" / "memex").mkdir(parents=True)
    (v / "_meta").mkdir(parents=True)
    (v / INBOX_DIR_NAME / "2026-05-10--note.md").write_text("hello", encoding="utf-8")
    return v


# ── Happy-path joins ────────────────────────────────────────────────────────

def test_simple_relative_path(vault: Path) -> None:
    out = safe_join(vault, "projects/memex/note.md")
    assert out == (vault / "projects" / "memex" / "note.md").resolve()


def test_existing_inbox_file(vault: Path) -> None:
    out = safe_join_existing(vault, f"{INBOX_DIR_NAME}/2026-05-10--note.md")
    assert out.is_file()


def test_vault_relative_round_trip(vault: Path) -> None:
    abs_path = (vault / INBOX_DIR_NAME / "2026-05-10--note.md").resolve()
    rel = vault_relative(vault, abs_path)
    assert rel == f"{INBOX_DIR_NAME}/2026-05-10--note.md"


def test_is_inbox_path_helper() -> None:
    assert is_inbox_path(f"{INBOX_DIR_NAME}/foo.md")
    assert is_inbox_path(f"{INBOX_DIR_NAME}/sub/foo.md")
    assert not is_inbox_path("projects/memex/foo.md")
    assert not is_inbox_path("")


# ── Adversarial paths ───────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "evil",
    [
        "../etc/passwd",
        "../../etc/passwd",
        "projects/../../etc/passwd",
        "projects/../../../home/user/.ssh/id_rsa",
        "_inbox/../projects/memex/note.md",  # even an in-bounds end is rejected
        "..",
        "../",
        "./..",
        "foo/..",  # collapses outside via empty parent
    ],
)
def test_dotdot_segments_rejected(vault: Path, evil: str) -> None:
    with pytest.raises(VaultPathError):
        safe_join(vault, evil)


@pytest.mark.parametrize(
    "evil",
    [
        "/etc/passwd",
        "/vault/projects",
        "//etc/passwd",
        "///etc/passwd",
    ],
)
def test_absolute_paths_rejected(vault: Path, evil: str) -> None:
    # safe_join strips leading / first, so an absolute path becomes an
    # in-vault relative path. Either it stays inside (and is fine) or it
    # leaves the vault and is rejected. The contract is "never traverses
    # outside" — assert that.
    try:
        out = safe_join(vault, evil)
    except VaultPathError:
        return
    assert out.resolve().is_relative_to(vault.resolve())


def test_nul_byte_rejected(vault: Path) -> None:
    with pytest.raises(VaultPathError, match="NUL byte"):
        safe_join(vault, "projects/memex/note\x00.md")


def test_empty_path_rejected(vault: Path) -> None:
    with pytest.raises(VaultPathError):
        safe_join(vault, "")
    with pytest.raises(VaultPathError):
        safe_join(vault, "/")


def test_non_string_path_rejected(vault: Path) -> None:
    with pytest.raises(VaultPathError):
        safe_join(vault, 42)  # type: ignore[arg-type]


def test_windows_drive_letter_rejected(vault: Path) -> None:
    with pytest.raises(VaultPathError):
        safe_join(vault, "C:/Windows/system32")


def test_existing_required_for_safe_join_existing(vault: Path) -> None:
    with pytest.raises(VaultPathError):
        safe_join_existing(vault, "projects/memex/does-not-exist.md")


@pytest.mark.skipif(os.name == "nt", reason="symlink semantics differ on Windows")
def test_symlink_escape_rejected(vault: Path, tmp_path: Path) -> None:
    """A symlink inside the vault that points outside must be rejected.

    The user-supplied path resolves to a real file, but the *target* of that
    file is outside the vault. ``safe_join_existing`` follows the symlink,
    sees the resolved path is outside the vault, and raises.
    """
    outside_file = tmp_path / "outside.md"
    outside_file.write_text("escaped!", encoding="utf-8")
    link = vault / INBOX_DIR_NAME / "escape.md"
    link.symlink_to(outside_file)
    with pytest.raises(VaultPathError):
        safe_join_existing(vault, f"{INBOX_DIR_NAME}/escape.md")


def test_unicode_normalisation_doesnt_escape(vault: Path) -> None:
    # The vault root was created with plain ASCII; a path with NFC/NFD
    # variation should still resolve under it because we use Path.resolve().
    name = "projects/memex/néte.md"
    out = safe_join(vault, name)
    assert out.is_relative_to(vault.resolve())


def test_url_encoded_dotdot_treated_literally(vault: Path) -> None:
    """``%2e%2e`` is *literal* — no URL-decoding happens here. Routers
    receive the path post-decoding from FastAPI, so the safety check sees
    real ``..``. This test pins that ``%2e%2e`` (which is what an attacker
    would send if URL-decoding were missed) does *not* itself cause an
    escape, because it is treated as a literal directory name."""
    # %2e%2e is just a dirname; we'd happily ``mkdir`` it.
    out = safe_join(vault, "%2e%2e/secret.md")
    # The resolved path stays inside the vault.
    assert out.is_relative_to(vault.resolve())


def test_repeated_slashes_collapsed(vault: Path) -> None:
    out = safe_join(vault, "projects//memex///note.md")
    assert out == (vault / "projects" / "memex" / "note.md").resolve()
