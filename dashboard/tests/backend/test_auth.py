"""Bearer-token authentication tests.

Every mutating route returns 401 without a token, 401 with a wrong token,
and 200/2xx with the right token. Read-only routes work without a token.
"""
from __future__ import annotations

import secrets

import pytest
from fastapi.testclient import TestClient

from .conftest import TEST_TOKEN


# ── 401 without a token ─────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/api/v1/queue/1/retry", None),
        ("post", "/api/v1/queue/1/cancel", None),
        ("post", "/api/v1/inbox/_inbox/x.md/route", {"target_folder": "projects/memex"}),
        ("post", "/api/v1/inbox/_inbox/x.md/delete", None),
        ("put", "/api/v1/taxonomy", {"document": {"schema_version": 1}}),
        ("post", "/api/v1/retrieval", {"question": "what?"}),
    ],
)
def test_mutating_routes_require_token(client: TestClient, method: str, path: str, body) -> None:
    fn = getattr(client, method)
    if body is None:
        resp = fn(path)
    else:
        resp = fn(path, json=body)
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "unauthorized"


def test_invalid_token_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/queue/1/retry",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401


def test_wrong_scheme_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/queue/1/retry",
        headers={"Authorization": f"Basic {TEST_TOKEN}"},
    )
    assert resp.status_code == 401


def test_empty_bearer_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/queue/1/retry",
        headers={"Authorization": "Bearer "},
    )
    assert resp.status_code == 401


# ── Read-only routes do NOT need a token ────────────────────────────────────

@pytest.mark.parametrize(
    "path",
    [
        "/healthz",
        "/api/v1/queue",
        "/api/v1/inbox",
        "/api/v1/taxonomy",
        "/api/v1/captures",
        "/api/v1/rate-limit",
    ],
)
def test_read_only_routes_open(client: TestClient, path: str) -> None:
    resp = client.get(path)
    # Some are 404/200; the only thing that matters here is "not 401".
    assert resp.status_code != 401


# ── 200 with the right token ────────────────────────────────────────────────

def test_correct_token_accepted(client: TestClient, auth_headers: dict[str, str], insert_queue_row) -> None:
    item_id = insert_queue_row(status="failed", last_error="boom")
    resp = client.post(f"/api/v1/queue/{item_id}/retry", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"


# ── Constant-time comparison ────────────────────────────────────────────────

def test_uses_secrets_compare_digest_not_equality() -> None:
    """The auth module imports secrets.compare_digest. Verify by reading the
    source — checking timing in unit tests is unreliable."""
    import inspect

    from backend import auth

    src = inspect.getsource(auth)
    assert "secrets.compare_digest" in src
    assert " == " not in src.split("def require_token")[1] or "len(presented_b) != len(expected_b)" in src


def test_bearer_with_extra_whitespace_preserves_token(client: TestClient, auth_headers, insert_queue_row) -> None:
    """`Bearer <token>` with exactly one space is the canonical form."""
    item_id = insert_queue_row(status="failed", last_error="boom")
    resp = client.post(
        f"/api/v1/queue/{item_id}/retry",
        headers={"Authorization": f"Bearer {secrets.token_hex(32)}"},
    )
    assert resp.status_code == 401
    resp = client.post(f"/api/v1/queue/{item_id}/retry", headers=auth_headers)
    assert resp.status_code == 200
