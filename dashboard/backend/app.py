"""FastAPI application factory for the dashboard backend.

Wires every router under ``/api/v1`` and (if the frontend ``dist/`` directory
exists) serves the built React bundle at ``/``. In development the operator
runs ``vite dev`` directly and proxies ``/api/*`` to this backend; in
production the same container ships the built static bundle.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from .config import Settings, load_settings
from .db import connect
from .logging import configure as configure_logging
from .logging import log_event
from .routers import (
    captures,
    health,
    inbox,
    queue,
    rate_limit,
    retrieval,
    taxonomy,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.db = connect(settings.db_path)
        log_event(
            "service_started",
            db_path=str(settings.db_path),
            vault_dir=str(settings.vault_dir),
            frontend_dist=str(settings.frontend_dist_dir) if settings.frontend_dist_dir else None,
        )
        try:
            yield
        finally:
            try:
                app.state.db.close()
            except Exception:
                pass
            log_event("service_stopped")

    app = FastAPI(
        title="Memex Dashboard",
        version="1.0.0",
        lifespan=lifespan,
        # No CORS middleware: the frontend is served from the same origin.
    )
    app.state.settings = settings
    # Allow tests to inject a fake claude_runner.invoke without monkeypatching
    # the imported symbol.
    app.state.claude_runner_invoke = None

    @app.middleware("http")
    async def access_log(  # type: ignore[misc]
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
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
            )

    app.include_router(health.router)
    app.include_router(queue.router)
    app.include_router(inbox.router)
    app.include_router(taxonomy.router)
    app.include_router(captures.router)
    app.include_router(rate_limit.router)
    app.include_router(retrieval.router)

    if settings.frontend_dist_dir and settings.frontend_dist_dir.is_dir():
        _mount_frontend(app, settings)

    return app


def _mount_frontend(app: FastAPI, settings: Settings) -> None:
    """Serve the built Vite bundle at ``/``.

    SPA routing is handled by sending ``index.html`` for any request that
    isn't a static asset and didn't match an API route. Mounting at the root
    must come last so the API routes take precedence.
    """
    dist = settings.frontend_dist_dir
    if dist is None:
        return
    assets_dir = dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    index_path = dist / "index.html"

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str = "") -> Response:
        # Try the exact static asset first (favicon.ico, etc.).
        if full_path:
            candidate = (dist / full_path).resolve()
            try:
                candidate.relative_to(dist.resolve())
            except ValueError:
                # Path traversal attempt — fall through to the SPA index.
                candidate = index_path
            if candidate.is_file():
                return FileResponse(candidate)
        if index_path.is_file():
            return FileResponse(index_path)
        raise StarletteHTTPException(status_code=404, detail="frontend not built")
