from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def _seed(client, auth_header, n: int) -> list[int]:
    ids: list[int] = []
    for i in range(n):
        r = await client.post(
            "/captures/text", json={"text": f"item {i}"}, headers=auth_header
        )
        assert r.status_code == 202
        ids.append(r.json()["id"])
    return ids


async def test_listing_newest_first_and_pagination(client, auth_header) -> None:
    ids = await _seed(client, auth_header, 5)
    page1 = (await client.get("/captures?limit=2", headers=auth_header)).json()
    assert [item["id"] for item in page1["items"]] == [ids[4], ids[3]]
    assert page1["next_cursor"] == ids[3]

    page2 = (
        await client.get(
            f"/captures?limit=2&cursor={page1['next_cursor']}", headers=auth_header
        )
    ).json()
    assert [item["id"] for item in page2["items"]] == [ids[2], ids[1]]


async def test_listing_filters_by_status(client, auth_header) -> None:
    await _seed(client, auth_header, 3)
    resp = await client.get("/captures?status=queued", headers=auth_header)
    items = resp.json()["items"]
    assert items
    assert all(i["status"] == "queued" for i in items)

    resp = await client.get("/captures?status=filed", headers=auth_header)
    assert resp.json()["items"] == []


async def test_listing_filters_by_source_type(client, auth_header) -> None:
    await _seed(client, auth_header, 2)
    await client.post(
        "/captures/url", json={"url": "https://example.com/"}, headers=auth_header
    )
    items = (
        await client.get("/captures?source_type=url", headers=auth_header)
    ).json()["items"]
    assert all(i["source_type"] == "url" for i in items)
    assert len(items) == 1


async def test_listing_invalid_status_is_422(client, auth_header) -> None:
    resp = await client.get("/captures?status=bogus", headers=auth_header)
    assert resp.status_code == 422
