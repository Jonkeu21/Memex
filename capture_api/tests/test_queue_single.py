from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_single_item_200(client, auth_header) -> None:
    r = await client.post(
        "/captures/text", json={"text": "x"}, headers=auth_header
    )
    item_id = r.json()["id"]
    got = await client.get(f"/captures/{item_id}", headers=auth_header)
    assert got.status_code == 200
    assert got.json()["id"] == item_id


async def test_single_item_404(client, auth_header) -> None:
    got = await client.get("/captures/9999999", headers=auth_header)
    assert got.status_code == 404
    assert got.json()["detail"]["error"]["code"] == "not_found"
