"""Captures browser tests."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def _write_note(vault_dir: Path, rel_path: str, **fm) -> Path:
    fm.setdefault("id", 1)
    fm.setdefault("source", "url")
    fm.setdefault("captured_at", "2026-05-09T12:00:00.000000Z")
    fm.setdefault("processed_at", "2026-05-09T12:01:00.000000Z")
    fm.setdefault("confidence", 0.85)
    fm.setdefault("taxonomy_path", "/".join(rel_path.split("/")[:-1]))
    fm.setdefault("tags", [])
    fm.setdefault("needs_review", False)
    fm.setdefault("title", rel_path.split("/")[-1].replace(".md", ""))
    yaml_lines = ["---"]
    for key, value in fm.items():
        if isinstance(value, list):
            yaml_lines.append(f"{key}: [" + ", ".join(repr(v) for v in value) + "]")
        elif isinstance(value, bool):
            yaml_lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            yaml_lines.append(f"{key}: {value}")
    yaml_lines.append("---")
    text = "\n".join(yaml_lines) + "\n\n# " + str(fm["title"]) + "\n\nbody\n"
    full = vault_dir / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(text, encoding="utf-8")
    return full


def test_list_empty_vault(client: TestClient) -> None:
    resp = client.get("/api/v1/captures")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []


def test_list_walks_para_folders(client: TestClient, vault_dir: Path) -> None:
    _write_note(vault_dir, "projects/memex/2026-05-09--alpha.md", title="Alpha")
    _write_note(vault_dir, "areas/2026-05-08--bravo.md", title="Bravo",
                captured_at="2026-05-08T12:00:00.000000Z")
    _write_note(vault_dir, "resources/ml-papers/2026-05-07--charlie.md", title="Charlie",
                captured_at="2026-05-07T12:00:00.000000Z")
    _write_note(vault_dir, "_inbox/2026-05-10--delta.md", title="Delta",
                captured_at="2026-05-10T12:00:00.000000Z", needs_review=True)
    resp = client.get("/api/v1/captures")
    assert resp.status_code == 200
    titles = [it["title"] for it in resp.json()["items"]]
    # Newest first.
    assert titles == ["Delta", "Alpha", "Bravo", "Charlie"]


def test_list_filter_by_folder(client: TestClient, vault_dir: Path) -> None:
    _write_note(vault_dir, "projects/memex/a.md", title="A")
    _write_note(vault_dir, "areas/b.md", title="B")
    resp = client.get("/api/v1/captures", params={"folder": "projects/memex"})
    titles = [it["title"] for it in resp.json()["items"]]
    assert titles == ["A"]


def test_list_search_q(client: TestClient, vault_dir: Path) -> None:
    _write_note(vault_dir, "projects/memex/2026-05-10--orchid.md", title="Orchid notes")
    _write_note(vault_dir, "projects/memex/2026-05-10--carrot.md", title="Carrot notes")
    resp = client.get("/api/v1/captures", params={"q": "orchid"})
    titles = [it["title"] for it in resp.json()["items"]]
    assert titles == ["Orchid notes"]


def test_list_filter_needs_review(client: TestClient, vault_dir: Path) -> None:
    _write_note(vault_dir, "_inbox/needs.md", needs_review=True, title="Needs")
    _write_note(vault_dir, "projects/memex/done.md", needs_review=False, title="Done")
    resp = client.get("/api/v1/captures", params={"needs_review": "true"})
    titles = [it["title"] for it in resp.json()["items"]]
    assert titles == ["Needs"]


def test_list_pagination(client: TestClient, vault_dir: Path) -> None:
    for i in range(5):
        _write_note(
            vault_dir,
            f"projects/memex/2026-05-{i + 1:02d}--n{i}.md",
            title=f"N{i}",
            captured_at=f"2026-05-{i + 1:02d}T12:00:00.000000Z",
        )
    resp = client.get("/api/v1/captures", params={"limit": 2})
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"] == 2
    resp2 = client.get("/api/v1/captures", params={"limit": 2, "cursor": 2})
    body2 = resp2.json()
    assert len(body2["items"]) == 2
    assert body2["next_cursor"] == 4


def test_get_body(client: TestClient, vault_dir: Path) -> None:
    _write_note(vault_dir, "projects/memex/note.md", title="Note")
    resp = client.get("/api/v1/captures/projects/memex/note.md")
    assert resp.status_code == 200
    body = resp.json()
    assert body["path"] == "projects/memex/note.md"
    assert body["front_matter"]["title"] == "Note"
    assert "body" in body["body"]


def test_get_body_invalid_path_400(client: TestClient) -> None:
    resp = client.get("/api/v1/captures/..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code == 400


def test_get_body_404(client: TestClient) -> None:
    resp = client.get("/api/v1/captures/projects/memex/nope.md")
    # safe_join_existing rejects with VaultPathError → 400
    assert resp.status_code == 400


def test_get_body_rejects_non_markdown(client: TestClient, vault_dir: Path) -> None:
    (vault_dir / "projects" / "memex" / "binary.bin").write_bytes(b"\x00\x01")
    resp = client.get("/api/v1/captures/projects/memex/binary.bin")
    assert resp.status_code == 400
