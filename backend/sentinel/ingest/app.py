"""FastAPI application factory for the Ingestion API."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from sentinel.common.config import get_settings
from sentinel.ingest import routers

logger = logging.getLogger("sentinel.ingest")


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit request body size before parsing."""

    def __init__(self, app, max_bytes: int = 32 * 1024) -> None:
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


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        response.headers["x-response-time-ms"] = f"{(time.perf_counter() - started) * 1000:.2f}"
        return response


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = FastAPI(
        title="API Sentinel Ingest",
        version="0.1.0",
        docs_url="/api/docs" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=32 * 1024)
    app.add_middleware(RequestContextMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["POST", "OPTIONS"],
            allow_headers=["Content-Type", "X-Source-Key", "X-Request-Id"],
        )

    app.include_router(routers.health.router)
    app.include_router(routers.events.router, prefix="/ingest/v1")

    return app
