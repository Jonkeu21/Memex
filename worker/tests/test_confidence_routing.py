"""Confidence-band routing rules."""
from __future__ import annotations

from worker.main import _route
from worker import taxonomy as tax


def test_above_autonomous_files(tmp_vault):
    t = tax.load(tmp_vault / "_meta" / "taxonomy.yml", tmp_vault)
    target, status, needs_review, taxonomy_path = _route(0.90, "resources/ml-papers", t)
    assert target == "resources/ml-papers"
    assert status == "filed"
    assert needs_review is False
    assert taxonomy_path == "resources/ml-papers"


def test_review_band_routes_to_matched_with_flag(tmp_vault):
    t = tax.load(tmp_vault / "_meta" / "taxonomy.yml", tmp_vault)
    target, status, needs_review, taxonomy_path = _route(0.70, "resources/ml-papers", t)
    assert target == "resources/ml-papers"
    assert status == "needs_review"
    assert needs_review is True
    assert taxonomy_path == "resources/ml-papers"


def test_below_review_routes_to_inbox(tmp_vault):
    t = tax.load(tmp_vault / "_meta" / "taxonomy.yml", tmp_vault)
    target, status, needs_review, taxonomy_path = _route(0.40, "resources/ml-papers", t)
    assert target == "_inbox"
    assert status == "needs_review"
    assert needs_review is True
    assert taxonomy_path == "_inbox"


def test_per_folder_override_used(tmp_vault):
    t = tax.load(tmp_vault / "_meta" / "taxonomy.yml", tmp_vault)
    # areas/health: autonomous=0.85, review=0.65 — confidence 0.82 is review band
    _, status, needs_review, _ = _route(0.82, "areas/health", t)
    assert status == "needs_review"
    assert needs_review is True


def test_per_folder_override_above_autonomous(tmp_vault):
    t = tax.load(tmp_vault / "_meta" / "taxonomy.yml", tmp_vault)
    _, status, _, _ = _route(0.86, "areas/health", t)
    assert status == "filed"
