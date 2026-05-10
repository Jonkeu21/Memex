"""Tests for the taxonomy loader and reload-per-batch semantics."""
from __future__ import annotations

from pathlib import Path

import pytest

from worker import taxonomy as tax


def test_load_valid(tmp_vault: Path) -> None:
    t = tax.load(tmp_vault / "_meta" / "taxonomy.yml", tmp_vault)
    assert t.schema_version == 1
    assert t.default_route == "_inbox"
    assert t.autonomous_threshold == 0.80
    assert t.review_threshold == 0.60
    assert "projects/memex" in t.folder_paths()


def test_resolve_thresholds_default(tmp_vault: Path) -> None:
    t = tax.load(tmp_vault / "_meta" / "taxonomy.yml", tmp_vault)
    a, r = t.resolve_thresholds("projects/memex")
    assert (a, r) == (0.80, 0.60)


def test_resolve_thresholds_override(tmp_vault: Path) -> None:
    t = tax.load(tmp_vault / "_meta" / "taxonomy.yml", tmp_vault)
    a, r = t.resolve_thresholds("areas/health")
    assert (a, r) == (0.85, 0.65)


def test_resolve_thresholds_unknown_folder_falls_back_to_global(tmp_vault: Path) -> None:
    t = tax.load(tmp_vault / "_meta" / "taxonomy.yml", tmp_vault)
    a, r = t.resolve_thresholds("does/not/exist")
    assert (a, r) == (0.80, 0.60)


def test_invalid_schema_version(tmp_vault: Path) -> None:
    p = tmp_vault / "_meta" / "taxonomy.yml"
    p.write_text("schema_version: 99\ndefault_route: _inbox\nfolders: []\n", encoding="utf-8")
    with pytest.raises(tax.TaxonomyError):
        tax.load(p, tmp_vault)


def test_path_with_leading_slash_rejected(tmp_vault: Path) -> None:
    p = tmp_vault / "_meta" / "taxonomy.yml"
    p.write_text(
        "schema_version: 1\n"
        "default_route: _inbox\n"
        "folders:\n"
        "  - path: /absolute\n"
        "    keywords: []\n",
        encoding="utf-8",
    )
    with pytest.raises(tax.TaxonomyError):
        tax.load(p, tmp_vault)


def test_path_with_dotdot_rejected(tmp_vault: Path) -> None:
    p = tmp_vault / "_meta" / "taxonomy.yml"
    p.write_text(
        "schema_version: 1\n"
        "default_route: _inbox\n"
        "folders:\n"
        "  - path: foo/../bar\n"
        "    keywords: []\n",
        encoding="utf-8",
    )
    with pytest.raises(tax.TaxonomyError):
        tax.load(p, tmp_vault)


def test_path_with_whitespace_rejected(tmp_vault: Path) -> None:
    p = tmp_vault / "_meta" / "taxonomy.yml"
    p.write_text(
        "schema_version: 1\n"
        "default_route: _inbox\n"
        "folders:\n"
        "  - path: \"foo bar\"\n"
        "    keywords: []\n",
        encoding="utf-8",
    )
    with pytest.raises(tax.TaxonomyError):
        tax.load(p, tmp_vault)


def test_duplicate_paths_rejected(tmp_vault: Path) -> None:
    p = tmp_vault / "_meta" / "taxonomy.yml"
    p.write_text(
        "schema_version: 1\n"
        "default_route: _inbox\n"
        "folders:\n"
        "  - path: foo\n"
        "    keywords: []\n"
        "  - path: foo\n"
        "    keywords: []\n",
        encoding="utf-8",
    )
    (tmp_vault / "foo").mkdir()
    with pytest.raises(tax.TaxonomyError):
        tax.load(p, tmp_vault)


def test_thresholds_out_of_range(tmp_vault: Path) -> None:
    p = tmp_vault / "_meta" / "taxonomy.yml"
    p.write_text(
        "schema_version: 1\n"
        "default_route: _inbox\n"
        "confidence:\n"
        "  autonomous_threshold: 0.5\n"
        "  review_threshold: 0.8\n"
        "folders: []\n",
        encoding="utf-8",
    )
    with pytest.raises(tax.TaxonomyError):
        tax.load(p, tmp_vault)


def test_default_route_must_exist(tmp_vault: Path, tmp_path: Path) -> None:
    p = tmp_vault / "_meta" / "taxonomy.yml"
    p.write_text(
        "schema_version: 1\n"
        "default_route: missing-folder\n"
        "folders: []\n",
        encoding="utf-8",
    )
    with pytest.raises(tax.TaxonomyError):
        tax.load(p, tmp_vault)


def test_load_missing_file(tmp_path: Path) -> None:
    with pytest.raises(tax.TaxonomyError):
        tax.load(tmp_path / "no.yml", tmp_path)


def test_root_must_be_mapping(tmp_vault: Path) -> None:
    p = tmp_vault / "_meta" / "taxonomy.yml"
    p.write_text("- list\n- root\n", encoding="utf-8")
    with pytest.raises(tax.TaxonomyError):
        tax.load(p, tmp_vault)


def test_reload_picks_up_edits(tmp_vault: Path) -> None:
    p = tmp_vault / "_meta" / "taxonomy.yml"
    t1 = tax.load(p, tmp_vault)
    assert t1.autonomous_threshold == 0.80
    p.write_text(
        "schema_version: 1\n"
        "default_route: _inbox\n"
        "confidence:\n"
        "  autonomous_threshold: 0.95\n"
        "  review_threshold: 0.75\n"
        "folders: []\n",
        encoding="utf-8",
    )
    t2 = tax.load(p, tmp_vault)
    assert t2.autonomous_threshold == 0.95
    assert t2.review_threshold == 0.75


def test_keywords_must_be_list(tmp_vault: Path) -> None:
    p = tmp_vault / "_meta" / "taxonomy.yml"
    p.write_text(
        "schema_version: 1\n"
        "default_route: _inbox\n"
        "folders:\n"
        "  - path: projects/memex\n"
        "    keywords: notalist\n",
        encoding="utf-8",
    )
    with pytest.raises(tax.TaxonomyError):
        tax.load(p, tmp_vault)


def test_invalid_override(tmp_vault: Path) -> None:
    p = tmp_vault / "_meta" / "taxonomy.yml"
    p.write_text(
        "schema_version: 1\n"
        "default_route: _inbox\n"
        "folders:\n"
        "  - path: projects/memex\n"
        "    keywords: []\n"
        "    confidence_override:\n"
        "      autonomous_threshold: 0.4\n"
        "      review_threshold: 0.6\n",
        encoding="utf-8",
    )
    with pytest.raises(tax.TaxonomyError):
        tax.load(p, tmp_vault)
