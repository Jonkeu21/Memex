"""FastAPI app factory, lifespan, route mounting, and access logging."""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from .config import Settings, load_settings
from .db import connect, run_migrations
from .logging import configure as configure_logging
from .logging import log_event
from .routes import capture, health
from .routes import queue as queue_routes


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        conn = connect(settings.db_path)
        run_migrations(conn)
        settings.inbox_dir.mkdir(parents=True, exist_ok=True)
        app.state.db = conn
        log_event(
            "service_started",
            db_path=str(settings.db_path),
            inbox_dir=str(settings.inbox_dir),
            max_upload_mb=settings.max_upload_mb,
        )
        try:
            yield
        finally:
            conn.close()
            log_event("service_stopped")

    app = FastAPI(
        title="Memex Capture API",
        version="1.0.0",
        lifespan=lifespan,
        # CORS hook: same-origin via Tailscale, so middleware is intentionally absent.
    )
    app.state.settings = settings

    app.include_router(health.router)
    app.include_router(capture.router)
    app.include_router(queue_routes.router)

    @app.middleware("http")
    async def access_log(  # type: ignore[misc]
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
        request.state.queue_item_id = None
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            log_event(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code if response else 500,
                duration_ms=duration_ms,
                queue_item_id=getattr(request.state, "queue_item_id", None),
            )

    return app
