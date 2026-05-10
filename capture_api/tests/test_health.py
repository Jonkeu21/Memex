from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app

pytestmark = pytest.mark.asyncio


async def test_healthz_ok(client) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200


async def test_readyz_503_when_db_unwritable(make_settings, auth_header, tmp_path: Path) -> None:
    bad_path = tmp_path / "nonexistent" / "deeply" / "nested.db"
    settings = make_settings(CAPTURE_DB_PATH=str(bad_path))
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        # Make the db path unwritable by replacing it with a directory after startup.
        bad_path.unlink(missing_ok=True)
        bad_path.mkdir(parents=True, exist_ok=True)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/readyz", headers=auth_header)
            assert r.status_code == 503
