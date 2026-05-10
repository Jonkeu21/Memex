from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.asyncio


async def test_50_concurrent_text_captures(app_and_client, auth_header) -> None:
    app, client = app_and_client

    async def post_one(i: int):
        r = await client.post(
            "/captures/text", json={"text": f"item-{i}"}, headers=auth_header
        )
        return r

    results = await asyncio.gather(*(post_one(i) for i in range(50)))
    assert all(r.status_code == 202 for r in results)
    ids = sorted(r.json()["id"] for r in results)
    assert len(set(ids)) == 50
    # Monotonically increasing — autoincrement guarantees this.
    assert ids == sorted(ids)
    n = app.state.db.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
    assert n == 50
