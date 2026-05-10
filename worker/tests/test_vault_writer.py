"""Vault writer: slug, filename collision, atomic write, front-matter rendering."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from worker import vault_writer as vw


def test_slugify_basic():
    assert vw.slugify("Hello World") == "hello-world"


def test_slugify_punctuation_collapses():
    assert vw.slugify("It's a Beautiful Day!!!") == "it-s-a-beautiful-day"


def test_slugify_diacritics():
    assert vw.slugify("Café Münster") == "cafe-munster"


def test_slugify_max_60():
    long = "a" * 200
    assert len(vw.slugify(long)) == 60


def test_slugify_empty():
    assert vw.slugify("") == "untitled"
    assert vw.slugify("///") == "untitled"


def test_slugify_strips_dashes():
    assert vw.slugify("--foo--bar--") == "foo-bar"


def test_build_filename_no_collision(tmp_path: Path):
    p = vw.build_filename(tmp_path, date(2026, 5, 10), "hello")
    assert p.name == "2026-05-10--hello.md"


def test_build_filename_collision_suffix(tmp_path: Path):
    (tmp_path / "2026-05-10--hello.md").write_text("a")
    p = vw.build_filename(tmp_path, date(2026, 5, 10), "hello")
    assert p.name == "2026-05-10--hello-2.md"
    p.write_text("b")
    p3 = vw.build_filename(tmp_path, date(2026, 5, 10), "hello")
    assert p3.name == "2026-05-10--hello-3.md"


def test_atomic_write_round_trip(tmp_path: Path):
    target = tmp_path / "sub" / "file.md"
    vw.atomic_write(target, "hello\n")
    assert target.read_text() == "hello\n"
    assert not (tmp_path / "sub" / "file.md.tmp").exists()


def test_atomic_write_crash_seam_leaves_tmp_no_target(tmp_path: Path):
    target = tmp_path / "file.md"
    with pytest.raises(vw.VaultWriteCrash):
        vw.atomic_write(target, "x", crash_after_temp=True)
    assert not target.exists()
    assert (tmp_path / "file.md.tmp").exists()


def test_front_matter_field_order_url():
    fm = vw.build_front_matter(
        queue_id=4123,
        source="url",
        captured_at="2026-05-10T14:22:01.123456Z",
        processed_at="2026-05-10T14:23:18.998012Z",
        confidence=0.87,
        taxonomy_path="resources/ml-papers",
        tags=["transformer", "Paper", "transformer"],
        needs_review=False,
        original_url="https://example.com/x",
    )
    rendered = fm.render()
    lines = [l for l in rendered.splitlines() if l and not l.startswith("---")]
    keys = [line.split(":", 1)[0] for line in lines]
    assert keys == [
        "id",
        "source",
        "captured_at",
        "processed_at",
        "confidence",
        "taxonomy_path",
        "tags",
        "needs_review",
        "original_url",
    ]
    assert "tags: [paper, transformer]" in rendered


def test_front_matter_voice_emits_attachment():
    fm = vw.build_front_matter(
        queue_id=1,
        source="voice",
        captured_at="2026-05-10T14:22:01.123456Z",
        processed_at="2026-05-10T14:23:18.998012Z",
        confidence=0.5,
        taxonomy_path="_inbox",
        tags=[],
        needs_review=True,
        attachment="_attachments/2026/05/voice.ogg",
    )
    rendered = fm.render()
    assert "attachment: _attachments/2026/05/voice.ogg" in rendered
    assert "original_url" not in rendered


def test_front_matter_inbox_taxonomy_path_value():
    fm = vw.build_front_matter(
        queue_id=2, source="text",
        captured_at="2026-05-10T14:22:01.123456Z",
        processed_at="2026-05-10T14:23:18.998012Z",
        confidence=0.1, taxonomy_path="_inbox",
        tags=[], needs_review=True,
    )
    assert "taxonomy_path: _inbox\n" in fm.render()


def test_render_note_structure():
    fm = vw.build_front_matter(
        queue_id=1, source="text",
        captured_at="t1", processed_at="t2",
        confidence=0.9, taxonomy_path="resources/ml-papers",
        tags=["a"], needs_review=False,
    )
    note = vw.render_note(front_matter=fm, title="My Note", summary="Summary text.", body_content="Body text.")
    assert note.startswith("---\n")
    assert "# My Note" in note
    assert "## Source" in note
    assert note.find("Summary text.") < note.find("## Source")


def test_write_note_returns_relative_path(tmp_vault: Path):
    fm = vw.build_front_matter(
        queue_id=1, source="text",
        captured_at="t1", processed_at="t2",
        confidence=0.9, taxonomy_path="projects/memex",
        tags=[], needs_review=False,
    )
    p = vw.write_note(
        vault_dir=tmp_vault, target_folder="projects/memex",
        captured_date=date(2026, 5, 10),
        title="Hello", summary="Summ.", body_content="Body.",
        front_matter=fm,
    )
    assert p == "projects/memex/2026-05-10--hello.md"
    assert (tmp_vault / p).exists()
