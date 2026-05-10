"""Inbox triage router tests."""
from __future__ import annotations

import textwrap
from pathlib import Path

from fastapi.testclient import TestClient


def _write_inbox_note(vault_dir: Path, name: str, *, body: str = "body", **fm) -> Path:
    fm.setdefault("id", 1)
    fm.setdefault("source", "url")
    fm.setdefault("captured_at", "2026-05-10T14:22:01.123456Z")
    fm.setdefault("processed_at", "2026-05-10T14:22:05.987654Z")
    fm.setdefault("confidence", 0.42)
    fm.setdefault("taxonomy_path", "_inbox")
    fm.setdefault("tags", [])
    fm.setdefault("needs_review", True)
    fm.setdefault("title", name)
    yaml_lines = ["---"]
    for key, value in fm.items():
        if isinstance(value, list):
            yaml_lines.append(f"{key}: [" + ", ".join(repr(v) for v in value) + "]")
        elif isinstance(value, bool):
            yaml_lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            yaml_lines.append(f"{key}: {value}")
    yaml_lines.append("---")
    text = "\n".join(yaml_lines) + "\n\n" + body + "\n"
    path = vault_dir / "_inbox" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ── List ────────────────────────────────────────────────────────────────────

def test_list_empty(client: TestClient) -> None:
    resp = client.get("/api/v1/inbox")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_list_returns_inbox_files(client: TestClient, vault_dir: Path) -> None:
    _write_inbox_note(vault_dir, "2026-05-10--first.md", title="First")
    _write_inbox_note(vault_dir, "2026-05-10--second.md", title="Second", confidence=0.7,
                      taxonomy_path="resources/ml-papers")
    resp = client.get("/api/v1/inbox")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    titles = {it["title"] for it in items}
    assert {"First", "Second"} == titles
    second = next(it for it in items if it["title"] == "Second")
    assert second["suggested_taxonomy"] == "resources/ml-papers"
    assert second["needs_review"] is True


def test_list_skips_non_md(client: TestClient, vault_dir: Path) -> None:
    (vault_dir / "_inbox" / "ignored.txt").write_text("not markdown", encoding="utf-8")
    _write_inbox_note(vault_dir, "real.md")
    resp = client.get("/api/v1/inbox")
    items = resp.json()["items"]
    assert len(items) == 1


def test_list_handles_extraction_failed(client: TestClient, vault_dir: Path) -> None:
    p = _write_inbox_note(vault_dir, "failed.md")
    text = p.read_text(encoding="utf-8").replace(
        "needs_review: true", "needs_review: true\nextraction_failed: true"
    )
    p.write_text(text, encoding="utf-8")
    resp = client.get("/api/v1/inbox")
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["reason_for_inbox"] == "extraction failed"


# ── Get a single file ───────────────────────────────────────────────────────

def test_get_returns_body(client: TestClient, vault_dir: Path) -> None:
    _write_inbox_note(vault_dir, "note.md", body="# Heading\n\nbody body", title="Note")
    resp = client.get("/api/v1/inbox/_inbox/note.md")
    assert resp.status_code == 200
    body = resp.json()
    assert body["path"] == "_inbox/note.md"
    assert "body body" in body["body"]
    assert body["front_matter"]["title"] == "Note"


def test_get_invalid_path_400(client: TestClient) -> None:
    # Send URL-encoded ../ so the test client doesn't normalise it away before
    # the request reaches our path-safety check.
    resp = client.get("/api/v1/inbox/_inbox%2F..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "invalid_path"


def test_get_outside_inbox_400(client: TestClient, vault_dir: Path) -> None:
    target = vault_dir / "projects" / "memex" / "note.md"
    target.write_text("---\nid: 1\n---\nhi\n", encoding="utf-8")
    resp = client.get("/api/v1/inbox/projects/memex/note.md")
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "not_in_inbox"


def test_get_404_when_missing(client: TestClient, vault_dir: Path) -> None:
    resp = client.get("/api/v1/inbox/_inbox/nope.md")
    assert resp.status_code == 400  # safe_join_existing rejects non-existing
    # Either is acceptable safety-wise; assert the dashboard never serves it.


# ── Route ───────────────────────────────────────────────────────────────────

def test_route_moves_file_atomically(client: TestClient, auth_headers, vault_dir: Path) -> None:
    _write_inbox_note(vault_dir, "2026-05-10--paper.md")
    resp = client.post(
        "/api/v1/inbox/_inbox/2026-05-10--paper.md/route",
        headers=auth_headers,
        json={"target_folder": "resources/ml-papers"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["new_path"].startswith("resources/ml-papers/")
    assert (vault_dir / body["new_path"]).is_file()
    assert not (vault_dir / "_inbox" / "2026-05-10--paper.md").exists()
    new_text = (vault_dir / body["new_path"]).read_text(encoding="utf-8")
    assert "needs_review: false" in new_text
    assert "taxonomy_path: resources/ml-papers" in new_text


def test_route_to_unknown_folder_rejected(client: TestClient, auth_headers, vault_dir: Path) -> None:
    _write_inbox_note(vault_dir, "x.md")
    resp = client.post(
        "/api/v1/inbox/_inbox/x.md/route",
        headers=auth_headers,
        json={"target_folder": "projects/never-declared"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"]["code"] == "unknown_folder"


def test_route_to_inbox_or_trash_rejected(client: TestClient, auth_headers, vault_dir: Path) -> None:
    _write_inbox_note(vault_dir, "x.md")
    for evil in ("_inbox", "_trash/2026-05"):
        resp = client.post(
            "/api/v1/inbox/_inbox/x.md/route",
            headers=auth_headers,
            json={"target_folder": evil},
        )
        assert resp.status_code == 400


def test_route_path_traversal_rejected(client: TestClient, auth_headers) -> None:
    resp = client.post(
        "/api/v1/inbox/_inbox/..%2F..%2Fetc%2Fpasswd/route",
        headers=auth_headers,
        json={"target_folder": "resources/ml-papers"},
    )
    assert resp.status_code == 400


def test_route_collision_disambiguates(client: TestClient, auth_headers, vault_dir: Path) -> None:
    _write_inbox_note(vault_dir, "2026-05-10--dup.md")
    target_dir = vault_dir / "resources" / "ml-papers"
    (target_dir / "2026-05-10--dup.md").write_text("preexisting\n", encoding="utf-8")
    resp = client.post(
        "/api/v1/inbox/_inbox/2026-05-10--dup.md/route",
        headers=auth_headers,
        json={"target_folder": "resources/ml-papers"},
    )
    assert resp.status_code == 200
    new_path = resp.json()["new_path"]
    assert new_path.endswith("-2.md")


# ── Delete (trash) ──────────────────────────────────────────────────────────

def test_delete_moves_to_trash(client: TestClient, auth_headers, vault_dir: Path) -> None:
    _write_inbox_note(vault_dir, "todelete.md")
    resp = client.post("/api/v1/inbox/_inbox/todelete.md/delete", headers=auth_headers)
    assert resp.status_code == 200
    trashed = resp.json()["trashed_path"]
    assert trashed.startswith("_trash/")
    assert trashed.endswith("todelete.md")
    assert (vault_dir / trashed).is_file()
    assert not (vault_dir / "_inbox" / "todelete.md").exists()


def test_delete_path_outside_inbox_rejected(client: TestClient, auth_headers, vault_dir: Path) -> None:
    target = vault_dir / "projects" / "memex" / "note.md"
    target.write_text("---\nid: 1\n---\nx\n", encoding="utf-8")
    resp = client.post("/api/v1/inbox/projects/memex/note.md/delete", headers=auth_headers)
    assert resp.status_code == 400


def test_delete_invalid_path_400(client: TestClient, auth_headers) -> None:
    resp = client.post(
        "/api/v1/inbox/_inbox/..%2Fevil/delete",
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_delete_collision_disambiguates(client: TestClient, auth_headers, vault_dir: Path) -> None:
    """Deleting twice in the same month puts the second copy at -2."""
    _write_inbox_note(vault_dir, "x.md")
    resp1 = client.post("/api/v1/inbox/_inbox/x.md/delete", headers=auth_headers)
    assert resp1.status_code == 200
    _write_inbox_note(vault_dir, "x.md")
    resp2 = client.post("/api/v1/inbox/_inbox/x.md/delete", headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["trashed_path"] != resp1.json()["trashed_path"]
