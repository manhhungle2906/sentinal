"""FastAPI application factory for the Core API."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from sentinel.common.config import get_settings
from sentinel.core import routers

logger = logging.getLogger("sentinel.core")

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id and measure request duration."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["x-request-id"] = request_id
        response.headers["x-response-time-ms"] = f"{duration_ms:.2f}"
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized request bodies before they are parsed."""

    def __init__(self, app, max_bytes: int = 64 * 1024) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    return Response(
                        content=b'{"detail":"request body too large"}',
                        status_code=413,
                        media_type="application/json",
                    )
            except ValueError:
                return Response(
                    content=b'{"detail":"invalid content-length"}',
                    status_code=400,
                    media_type="application/json",
                )
        return await call_next(request)


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = FastAPI(
        title="API Sentinel Core",
        version="0.1.0",
        docs_url="/api/docs" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
    )

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=64 * 1024)
    app.add_middleware(RequestContextMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-Id"],
        )

    app.include_router(routers.health.router)
    app.include_router(routers.auth.router, prefix="/api/auth")
    app.include_router(routers.workspaces.router, prefix="/api/workspaces")
    app.include_router(routers.sources.router, prefix="/api/sources")
    app.include_router(routers.monitoring.router, prefix="/api")
    app.include_router(routers.investigation.router, prefix="/api/alerts")

    return app
