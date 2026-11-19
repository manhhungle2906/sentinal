"""Health endpoints for Core and Ingest, plus detector heartbeat inspection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from sentinel.common.clock import utcnow
from sentinel.common.contracts import HealthResponse, ReadyResponse
from sentinel.common.db import get_db
from sentinel.common.models import DetectorHeartbeat

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=HealthResponse)
def live() -> HealthResponse:
    """Liveness: the process is up. No internal details are exposed."""
    return HealthResponse(status="ok", service="core", checked_at=utcnow())


@router.get("/health/ready", response_model=ReadyResponse)
def ready(db: Session = Depends(get_db)) -> ReadyResponse:
    """Readiness: the database is reachable."""
    database_ok = "unavailable"
    try:
        db.execute(text("SELECT 1"))
        database_ok = "ok"
    except Exception:
        database_ok = "unavailable"
    overall = "ok" if database_ok == "ok" else "degraded"
    return ReadyResponse(
        status=overall,
        service="core",
        checked_at=utcnow(),
        database=database_ok,
    )


def detector_heartbeat_age(db: Session) -> datetime | None:
    """Return the age of the detector heartbeat, or None when never seen."""
    row = db.get(DetectorHeartbeat, 1)
    if row is None:
        return None
    last_seen = row.last_seen_at
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=UTC)
    return utcnow() - last_seen


def detector_is_fresh(db: Session, max_age_seconds: int = 60) -> bool:
    age = detector_heartbeat_age(db)
    return age is not None and age <= timedelta(seconds=max_age_seconds)


@router.get("/health/detector", response_model=HealthResponse)
def detector_health(db: Session = Depends(get_db)) -> HealthResponse:
    """Detector liveness as observed by Core (used by the smoke script)."""
    fresh = detector_is_fresh(db)
    return HealthResponse(
        status="ok" if fresh else "degraded",
        service="detector",
        checked_at=utcnow(),
    )
