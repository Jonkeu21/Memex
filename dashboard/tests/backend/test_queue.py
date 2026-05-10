"""Queue router tests."""
from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient


def test_list_empty(client: TestClient) -> None:
    resp = client.get("/api/v1/queue")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


def test_list_filter_by_status(client: TestClient, insert_queue_row) -> None:
    insert_queue_row(status="queued")
    insert_queue_row(status="filed", confidence=0.9, vault_path="resources/x.md")
    insert_queue_row(status="failed", last_error="oops")
    resp = client.get("/api/v1/queue", params={"status": "filed"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "filed"


def test_list_pagination(client: TestClient, insert_queue_row) -> None:
    ids = [insert_queue_row() for _ in range(5)]
    resp = client.get("/api/v1/queue", params={"limit": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"] is not None
    # Newest first.
    assert body["items"][0]["id"] == ids[-1]


def test_list_filter_by_source_type(client: TestClient, insert_queue_row) -> None:
    insert_queue_row(source_type="text", source_payload='{"text":"hi"}')
    insert_queue_row(source_type="url", source_payload='{"url":"https://x"}')
    resp = client.get("/api/v1/queue", params={"source_type": "url"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["source_type"] == "url"


def test_get_single_404(client: TestClient) -> None:
    resp = client.get("/api/v1/queue/9999")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "not_found"


def test_get_single_returns_full_row(client: TestClient, insert_queue_row) -> None:
    item_id = insert_queue_row(
        status="filed",
        confidence=0.91,
        vault_path="resources/ml-papers/2026-05-10--note.md",
    )
    resp = client.get(f"/api/v1/queue/{item_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == item_id
    assert body["confidence"] == 0.91
    assert body["vault_path"] == "resources/ml-papers/2026-05-10--note.md"


# ── retry / cancel ──────────────────────────────────────────────────────────

def test_retry_failed_item(client: TestClient, auth_headers, insert_queue_row, db_path) -> None:
    item_id = insert_queue_row(status="failed", last_error="boom", attempts=5)
    resp = client.post(f"/api/v1/queue/{item_id}/retry", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"id": item_id, "status": "queued"}
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status, last_error FROM queue WHERE id=?", (item_id,)).fetchone()
    conn.close()
    assert row[0] == "queued"
    assert row[1] is None


def test_retry_needs_review_item(client: TestClient, auth_headers, insert_queue_row) -> None:
    item_id = insert_queue_row(status="needs_review")
    resp = client.post(f"/api/v1/queue/{item_id}/retry", headers=auth_headers)
    assert resp.status_code == 200


def test_retry_processing_item_rejected(client: TestClient, auth_headers, insert_queue_row) -> None:
    item_id = insert_queue_row(status="processing")
    resp = client.post(f"/api/v1/queue/{item_id}/retry", headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "invalid_status"


def test_retry_404(client: TestClient, auth_headers) -> None:
    resp = client.post("/api/v1/queue/9999/retry", headers=auth_headers)
    assert resp.status_code == 404


def test_cancel_queued_item(client: TestClient, auth_headers, insert_queue_row, db_path) -> None:
    item_id = insert_queue_row(status="queued")
    resp = client.post(f"/api/v1/queue/{item_id}/cancel", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"id": item_id, "status": "failed"}
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT status, last_error FROM queue WHERE id=?", (item_id,)
    ).fetchone()
    conn.close()
    assert row[0] == "failed"
    assert "cancelled" in (row[1] or "").lower()


def test_cancel_needs_review_item(client: TestClient, auth_headers, insert_queue_row) -> None:
    item_id = insert_queue_row(status="needs_review")
    resp = client.post(f"/api/v1/queue/{item_id}/cancel", headers=auth_headers)
    assert resp.status_code == 200


def test_cancel_filed_item_rejected(client: TestClient, auth_headers, insert_queue_row) -> None:
    item_id = insert_queue_row(status="filed")
    resp = client.post(f"/api/v1/queue/{item_id}/cancel", headers=auth_headers)
    assert resp.status_code == 409


def test_cancel_404(client: TestClient, auth_headers) -> None:
    resp = client.post("/api/v1/queue/9999/cancel", headers=auth_headers)
    assert resp.status_code == 404
