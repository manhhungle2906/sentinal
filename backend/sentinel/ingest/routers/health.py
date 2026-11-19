"""Health endpoints for the Ingestion API."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from sentinel.common.clock import utcnow
from sentinel.common.contracts import HealthResponse, ReadyResponse
from sentinel.common.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse(status="ok", service="ingest", checked_at=utcnow())


@router.get("/health/ready", response_model=ReadyResponse)
def ready(db: Session = Depends(get_db)) -> ReadyResponse:
    try:
        db.execute(text("SELECT 1"))
        database_ok = "ok"
    except Exception:
        database_ok = "unavailable"
    return ReadyResponse(
        status="ok" if database_ok == "ok" else "degraded",
        service="ingest",
        checked_at=utcnow(),
        database=database_ok,
    )
