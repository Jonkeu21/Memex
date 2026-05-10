"""Rate-limit telemetry endpoint tests."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient


def _iso(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def test_empty_when_no_calls(client: TestClient) -> None:
    resp = client.get("/api/v1/rate-limit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True  # table exists, just no rows
    assert body["total_24h"] == 0
    assert body["recent_calls"] == []


def test_unavailable_when_table_missing(client: TestClient, db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TABLE claude_calls")
    conn.commit()
    conn.close()
    resp = client.get("/api/v1/rate-limit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["recent_calls"] == []


def test_returns_recent_calls(client: TestClient, insert_claude_call) -> None:
    insert_claude_call(service="worker", purpose="file", exit_code=0)
    insert_claude_call(service="dashboard", purpose="retrieve", exit_code=0)
    insert_claude_call(service="telegram_bot", purpose="retrieve", exit_code=-1)
    resp = client.get("/api/v1/rate-limit")
    body = resp.json()
    assert body["available"] is True
    assert body["total_24h"] == 3
    services = {c["service"] for c in body["recent_calls"]}
    assert services == {"worker", "dashboard", "telegram_bot"}


def test_services_breakdown_24h(client: TestClient, insert_claude_call) -> None:
    insert_claude_call(service="worker")
    insert_claude_call(service="worker")
    insert_claude_call(service="telegram_bot")
    resp = client.get("/api/v1/rate-limit")
    body = resp.json()
    assert body["services_breakdown_24h"]["worker"] == 2
    assert body["services_breakdown_24h"]["telegram_bot"] == 1


def test_5m_error_rate(client: TestClient, insert_claude_call) -> None:
    now = datetime.now(timezone.utc)
    # Inside the 5-minute window: 1 success, 2 failures
    insert_claude_call(ts=_iso(now - timedelta(minutes=1)), exit_code=0)
    insert_claude_call(ts=_iso(now - timedelta(minutes=2)), exit_code=-1)
    insert_claude_call(ts=_iso(now - timedelta(minutes=3)), exit_code=1)
    # Older than 5 minutes — excluded from 5m rate
    insert_claude_call(ts=_iso(now - timedelta(minutes=10)), exit_code=-1)
    resp = client.get("/api/v1/rate-limit")
    body = resp.json()
    # 2 errors / 3 in-window = 0.6667
    assert abs(body["error_rate_5m"] - 2 / 3) < 0.01


def test_24h_horizon_excludes_older_rows(client: TestClient, insert_claude_call) -> None:
    now = datetime.now(timezone.utc)
    insert_claude_call(ts=_iso(now - timedelta(hours=1)))
    insert_claude_call(ts=_iso(now - timedelta(hours=25)))
    resp = client.get("/api/v1/rate-limit")
    body = resp.json()
    assert body["total_24h"] == 1


def test_by_hour_buckets(client: TestClient, insert_claude_call) -> None:
    now = datetime.now(timezone.utc)
    same_hour_a = now.replace(minute=10, second=0, microsecond=0)
    same_hour_b = now.replace(minute=45, second=0, microsecond=0)
    other_hour = (now - timedelta(hours=2)).replace(minute=5, second=0, microsecond=0)
    insert_claude_call(ts=_iso(same_hour_a), service="worker", input_tokens=100, output_tokens=50)
    insert_claude_call(ts=_iso(same_hour_b), service="worker", input_tokens=200, output_tokens=80)
    insert_claude_call(ts=_iso(other_hour), service="dashboard", input_tokens=10, output_tokens=5)
    resp = client.get("/api/v1/rate-limit")
    body = resp.json()
    buckets = body["by_hour"]
    # one bucket for the (current hour, worker) pair, one for (other_hour, dashboard)
    same_hour_bucket = [b for b in buckets if b["service"] == "worker"]
    assert len(same_hour_bucket) == 1
    assert same_hour_bucket[0]["count"] == 2
    assert same_hour_bucket[0]["input_tokens"] == 300


def test_recent_calls_limited_to_20(client: TestClient, insert_claude_call) -> None:
    for _ in range(30):
        insert_claude_call()
    resp = client.get("/api/v1/rate-limit")
    body = resp.json()
    assert len(body["recent_calls"]) == 20
