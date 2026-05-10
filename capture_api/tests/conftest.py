from __future__ import annotations

import sys
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings, load_settings  # noqa: E402
from app.main import create_app  # noqa: E402


TEST_TOKEN = "test-token-value"


def _build_settings(tmp_path: Path, **overrides: str) -> Settings:
    env = {
        "MEMEX_CAPTURE_TOKEN_test": TEST_TOKEN,
        "CAPTURE_DB_PATH": str(tmp_path / "queue.db"),
        "CAPTURE_INBOX_DIR": str(tmp_path / "inbox"),
        "CAPTURE_MAX_UPLOAD_MB": "1",
        "LOG_LEVEL": "DEBUG",
    }
    env.update(overrides)
    return load_settings(env)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return _build_settings(tmp_path)


@pytest.fixture
def make_settings(tmp_path: Path):
    def _factory(**overrides: str) -> Settings:
        return _build_settings(tmp_path, **overrides)
    return _factory


@pytest_asyncio.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest_asyncio.fixture
async def app_and_client(settings: Settings) -> AsyncIterator[tuple[object, AsyncClient]]:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield app, ac


@pytest.fixture
def auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {TEST_TOKEN}"}
