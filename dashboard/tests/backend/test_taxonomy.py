"""Taxonomy router + parser tests."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.taxonomy_io import TaxonomyError, parse, render
from backend.schemas import (
    TaxonomyConfidence,
    TaxonomyDocument,
    TaxonomyFolder,
    TaxonomyOverride,
)


def test_parse_minimum_valid_doc() -> None:
    raw = "schema_version: 1\ndefault_route: _inbox\nconfidence:\n  autonomous_threshold: 0.8\n  review_threshold: 0.6\nfolders: []\n"
    loaded = parse(raw)
    assert loaded.document.schema_version == 1
    assert loaded.document.default_route == "_inbox"
    assert loaded.document.folders == []


def test_parse_with_folders_and_overrides() -> None:
    raw = """
    schema_version: 1
    default_route: _inbox
    confidence:
      autonomous_threshold: 0.80
      review_threshold: 0.60
    folders:
      - path: areas/health
        description: "Health logs"
        keywords: [sleep, hrv]
        confidence_override:
          autonomous_threshold: 0.85
          review_threshold: 0.65
    """
    loaded = parse(raw)
    assert len(loaded.document.folders) == 1
    folder = loaded.document.folders[0]
    assert folder.path == "areas/health"
    assert folder.confidence_override is not None
    assert folder.confidence_override.autonomous_threshold == 0.85


def test_parse_rejects_bad_yaml() -> None:
    with pytest.raises(TaxonomyError):
        parse("schema_version: [1\nfolders: -\n")


def test_parse_rejects_wrong_schema_version() -> None:
    raw = "schema_version: 99\ndefault_route: _inbox\nfolders: []\n"
    with pytest.raises(TaxonomyError, match="schema_version"):
        parse(raw)


def test_parse_rejects_dotdot_path() -> None:
    raw = (
        "schema_version: 1\ndefault_route: _inbox\nconfidence: {autonomous_threshold: 0.8, review_threshold: 0.6}\n"
        "folders:\n  - path: ../etc\n    keywords: []\n    confidence_override: null\n    description: \"\"\n"
    )
    with pytest.raises(TaxonomyError, match=r"\.\."):
        parse(raw)


def test_parse_rejects_absolute_path() -> None:
    raw = (
        "schema_version: 1\ndefault_route: _inbox\nconfidence: {autonomous_threshold: 0.8, review_threshold: 0.6}\n"
        "folders:\n  - path: /etc\n    keywords: []\n    confidence_override: null\n    description: \"\"\n"
    )
    with pytest.raises(TaxonomyError):
        parse(raw)


def test_parse_rejects_whitespace_in_path() -> None:
    raw = (
        "schema_version: 1\ndefault_route: _inbox\nconfidence: {autonomous_threshold: 0.8, review_threshold: 0.6}\n"
        "folders:\n  - path: \"foo bar\"\n    keywords: []\n    confidence_override: null\n    description: \"\"\n"
    )
    with pytest.raises(TaxonomyError):
        parse(raw)


def test_parse_rejects_duplicate_paths() -> None:
    raw = """
    schema_version: 1
    default_route: _inbox
    confidence: {autonomous_threshold: 0.8, review_threshold: 0.6}
    folders:
      - {path: a, keywords: [], confidence_override: null, description: ""}
      - {path: a, keywords: [], confidence_override: null, description: ""}
    """
    with pytest.raises(TaxonomyError, match="duplicate"):
        parse(raw)


def test_parse_rejects_threshold_inversion() -> None:
    raw = (
        "schema_version: 1\ndefault_route: _inbox\nconfidence:\n"
        "  autonomous_threshold: 0.5\n  review_threshold: 0.9\nfolders: []\n"
    )
    with pytest.raises(TaxonomyError):
        parse(raw)


def test_parse_rejects_excessive_depth() -> None:
    deep = "/".join(["a"] * 8)
    raw = (
        f"schema_version: 1\ndefault_route: _inbox\nconfidence: {{autonomous_threshold: 0.8, review_threshold: 0.6}}\n"
        f"folders:\n  - path: {deep}\n    keywords: []\n    confidence_override: null\n    description: \"\"\n"
    )
    with pytest.raises(TaxonomyError, match="depth"):
        parse(raw)


def test_render_round_trips() -> None:
    doc = TaxonomyDocument(
        schema_version=1,
        default_route="_inbox",
        confidence=TaxonomyConfidence(autonomous_threshold=0.8, review_threshold=0.6),
        folders=[
            TaxonomyFolder(
                path="resources/ml-papers",
                description="ML papers",
                keywords=["paper", "eval"],
                confidence_override=None,
            ),
        ],
    )
    text = render(doc)
    parsed = parse(text)
    assert parsed.document.folders[0].path == "resources/ml-papers"


def test_render_with_override() -> None:
    doc = TaxonomyDocument(
        folders=[
            TaxonomyFolder(
                path="areas/health",
                description="health",
                keywords=["sleep"],
                confidence_override=TaxonomyOverride(
                    autonomous_threshold=0.9, review_threshold=0.7
                ),
            ),
        ],
    )
    text = render(doc)
    assert "autonomous_threshold: 0.9" in text
    parsed = parse(text)
    assert parsed.document.folders[0].confidence_override is not None
    assert parsed.document.folders[0].confidence_override.autonomous_threshold == 0.9


# ── HTTP endpoint ───────────────────────────────────────────────────────────

def test_get_taxonomy(client: TestClient, vault_dir: Path) -> None:
    resp = client.get("/api/v1/taxonomy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["document"]["schema_version"] == 1
    paths = [f["path"] for f in body["document"]["folders"]]
    assert "projects/memex" in paths


def test_get_taxonomy_when_missing_returns_default(client: TestClient, vault_dir: Path) -> None:
    (vault_dir / "_meta" / "taxonomy.yml").unlink()
    resp = client.get("/api/v1/taxonomy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["document"]["schema_version"] == 1
    assert body["document"]["folders"] == []


def test_put_taxonomy_writes_atomically(client: TestClient, auth_headers, vault_dir: Path) -> None:
    new_doc = {
        "schema_version": 1,
        "default_route": "_inbox",
        "confidence": {"autonomous_threshold": 0.8, "review_threshold": 0.6},
        "folders": [
            {
                "path": "areas/health",
                "description": "health logs",
                "keywords": ["sleep", "hrv"],
                "confidence_override": None,
            }
        ],
    }
    resp = client.put(
        "/api/v1/taxonomy",
        headers=auth_headers,
        json={"document": new_doc},
    )
    assert resp.status_code == 200, resp.text
    on_disk = (vault_dir / "_meta" / "taxonomy.yml").read_text(encoding="utf-8")
    assert "areas/health" in on_disk
    parsed = yaml.safe_load(on_disk)
    assert parsed["folders"][0]["path"] == "areas/health"


def test_put_taxonomy_rejects_invalid(client: TestClient, auth_headers) -> None:
    bad = {
        "schema_version": 1,
        "default_route": "_inbox",
        "confidence": {"autonomous_threshold": 0.5, "review_threshold": 0.9},
        "folders": [],
    }
    resp = client.put(
        "/api/v1/taxonomy",
        headers=auth_headers,
        json={"document": bad},
    )
    assert resp.status_code == 400


def test_put_taxonomy_rejects_dotdot(client: TestClient, auth_headers) -> None:
    bad = {
        "schema_version": 1,
        "default_route": "_inbox",
        "confidence": {"autonomous_threshold": 0.8, "review_threshold": 0.6},
        "folders": [
            {"path": "../etc", "description": "", "keywords": [], "confidence_override": None}
        ],
    }
    resp = client.put(
        "/api/v1/taxonomy",
        headers=auth_headers,
        json={"document": bad},
    )
    assert resp.status_code == 400


def test_put_taxonomy_does_not_corrupt_on_failure(client: TestClient, auth_headers, vault_dir: Path) -> None:
    """A failed PUT must not change the on-disk taxonomy."""
    original = (vault_dir / "_meta" / "taxonomy.yml").read_text(encoding="utf-8")
    bad = {
        "schema_version": 1,
        "default_route": "_inbox",
        "confidence": {"autonomous_threshold": 0.5, "review_threshold": 0.9},
        "folders": [],
    }
    client.put("/api/v1/taxonomy", headers=auth_headers, json={"document": bad})
    after = (vault_dir / "_meta" / "taxonomy.yml").read_text(encoding="utf-8")
    assert after == original
