"""Demo API — a small ordinary API whose requests are instrumented.

The middleware emits whitelisted request metadata to the Sentinel ingestion
endpoint. It never emits bodies, headers or credentials.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("sentinel.demo")

INGEST_URL = os.environ.get("SENTINEL_INGEST_URL", "http://ingest:8000/ingest/v1/events")
SOURCE_KEY = os.environ.get("SENTINEL_SOURCE_KEY", "")

app = FastAPI(title="API Sentinel Demo API", version="0.1.0")

# The reserved documentation IP range (RFC 5737) is used for demo telemetry.
DEMO_SOURCE_IP = os.environ.get("SENTINEL_DEMO_IP", "203.0.113.10")

# Route templates are declared explicitly so the demo never reports a raw path.
ROUTE_TEMPLATES = {
    "/": "GET /",
    "/products": "GET /products",
    "/products/{product_id}": "GET /products/{product_id}",
    "/login": "POST /login",
}

PRODUCTS = [
    {"id": "p-1001", "name": "Field Notebook", "price": 12.5},
    {"id": "p-1002", "name": "Desk Lamp", "price": 34.0},
    {"id": "p-1003", "name": "Cable Organizer", "price": 7.25},
]


def route_template_for(path: str, method: str) -> str:
    """Map a request path to its declared route template."""
    if path == "/" and method == "GET":
        return "GET /"
    if path == "/products" and method == "GET":
        return "GET /products"
    if path.startswith("/products/") and method == "GET":
        return "GET /products/{product_id}"
    if path == "/login" and method == "POST":
        return "POST /login"
    return f"{method} {path}"


def split_route(template: str) -> tuple[str, str]:
    method, _, path = template.partition(" ")
    return method, path


@app.middleware("http")
async def emit_event(request: Request, call_next):
    started = datetime.now(UTC)
    response = await call_next(request)
    duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)

    path = request.url.path
    # The health probes are infrastructure traffic, not demo activity.
    if path.startswith("/health"):
        return response

    template = route_template_for(path, request.method)
    method, path = split_route(template)

    event_type = "login_failed" if path == "/login" and response.status_code == 401 else "request"

    await publish_event(
        event_id=uuid.uuid4(),
        event_type=event_type,
        source_ip=DEMO_SOURCE_IP,
        route_template=template,
        method=method,
        status_code=response.status_code,
        duration_ms=duration_ms,
        occurred_at=started,
    )
    return response


async def publish_event(**event) -> None:
    """Send one event to the ingestion API. Failures are logged, never raised."""
    if not SOURCE_KEY:
        logger.warning("SENTINEL_SOURCE_KEY is not set; the demo event was not published")
        return
    payload = {
        "event_id": str(event["event_id"]),
        "event_type": event["event_type"],
        "occurred_at": event["occurred_at"].isoformat(),
        "source_ip": event["source_ip"],
        "route_template": event["route_template"],
        "method": event["method"],
        "status_code": event["status_code"],
        "duration_ms": event["duration_ms"],
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                INGEST_URL, json=payload, headers={"X-Source-Key": SOURCE_KEY}
            )
        logger.info("published %s -> %s", payload["route_template"], response.status_code)
    except Exception:
        logger.exception("could not publish the demo event")


@app.get("/health/live")
def live() -> dict:
    return {"status": "ok", "service": "demo"}


@app.get("/health/ready")
def ready() -> dict:
    return {"status": "ok", "service": "demo"}


@app.get("/")
def index() -> Response:
    return JSONResponse(
        {
            "service": "API Sentinel demo API",
            "products": ["/products", "/products/{id}", "/login"],
        }
    )


@app.get("/products")
def list_products() -> Response:
    return JSONResponse({"items": PRODUCTS})


@app.get("/products/{product_id}")
def get_product(product_id: str) -> Response:
    for product in PRODUCTS:
        if product["id"] == product_id:
            return JSONResponse(product)
    return JSONResponse({"detail": "not found"}, status_code=404)


@app.post("/login")
def login() -> Response:
    """A demo sign-in. Any input fails, so the failure path can be demonstrated."""
    return JSONResponse({"detail": "invalid credentials"}, status_code=401)
