"""Event ingestion endpoint."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sentinel.common.clock import utcnow
from sentinel.common.config import Settings, get_settings
from sentinel.common.contracts import IngestEventRequest, IngestEventResponse
from sentinel.common.db import get_db
from sentinel.common.models import ApiSource, DetectorJob, SecurityEvent
from sentinel.common.rate_limit import SlidingWindowRateLimiter
from sentinel.common.security import token_digest

router = APIRouter(tags=["ingest"])


def _build_ingest_limiter() -> SlidingWindowRateLimiter:
    """Build the per-source ingestion limiter for the configured limit.

    The limit is read from the environment so an isolated demo environment can
    raise it without changing the production default.
    """
    limit = get_settings().ingestion_rate_limit_per_minute
    return SlidingWindowRateLimiter(limit=limit, window_seconds=60)


_ingest_limiter = _build_ingest_limiter()


def authenticate_source(db: Session, raw_key: str | None) -> ApiSource:
    """Resolve an ingestion key to an active source.

    Unknown, revoked or malformed keys all produce 401 without leaking
    which of the two failed.
    """
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="ingestion credential required"
        )
    source = db.execute(
        select(ApiSource).where(ApiSource.key_digest == token_digest(raw_key))
    ).scalar_one_or_none()
    if source is None or source.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid ingestion credential"
        )
    return source


@router.post(
    "/events",
    response_model=IngestEventResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a security event",
)
def ingest_event(
    payload: IngestEventRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    x_source_key: str | None = Header(default=None, alias="X-Source-Key"),
) -> IngestEventResponse:
    """Persist a validated event and queue it for detection.

    - New event -> 202
    - Identical retry of an accepted event -> 200
    - Same event id with different validated content -> 409
    """
    source = authenticate_source(db, x_source_key)

    allowed, _ = _ingest_limiter.check(str(source.id), utcnow())
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="ingestion rate limit exceeded for this source",
        )

    existing = db.execute(
        select(SecurityEvent).where(
            SecurityEvent.source_id == source.id,
            SecurityEvent.event_uuid == payload.event_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if _same_content(existing, payload):
            # An identical retry of an accepted event is a success, not a
            # new acceptance.
            return Response(
                content=IngestEventResponse(
                    event_id=existing.event_uuid,
                    status="duplicate",
                    received_at=existing.received_at,
                ).model_dump_json(),
                status_code=status.HTTP_200_OK,
                media_type="application/json",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="event id already exists with different content",
        )

    received_at = utcnow()
    event = SecurityEvent(
        source_id=source.id,
        event_uuid=payload.event_id,
        received_at=received_at,
        request_at=payload.occurred_at,
        source_ip=str(payload.source_ip),
        route_template=payload.route_template,
        method=payload.method,
        status_code=payload.status_code,
        duration_ms=payload.duration_ms,
        event_type=payload.event_type,
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="event id already exists with different content",
        ) from exc

    # The event and its detection job are created in the same transaction.
    db.add(DetectorJob(event_id=event.id, status="pending"))
    db.commit()
    db.refresh(event)
    return IngestEventResponse(
        event_id=event.event_uuid, status="accepted", received_at=event.received_at
    )


def _same_content(event: SecurityEvent, payload: IngestEventRequest) -> bool:
    """Compare the validated content of a retry against the stored event."""
    stored_request_at = event.request_at
    if stored_request_at is not None and stored_request_at.tzinfo is None:
        stored_request_at = stored_request_at.replace(tzinfo=UTC)
    payload_request_at = payload.occurred_at
    if payload_request_at is not None and payload_request_at.tzinfo is None:
        payload_request_at = payload_request_at.replace(tzinfo=UTC)

    return (
        str(event.source_ip) == str(payload.source_ip)
        and event.route_template == payload.route_template
        and event.method == payload.method
        and event.status_code == payload.status_code
        and event.duration_ms == payload.duration_ms
        and event.event_type == payload.event_type
        and stored_request_at == payload_request_at
    )


def new_event_uuid() -> uuid.UUID:
    return uuid.uuid4()


def utc_timestamp() -> datetime:
    return datetime.now(UTC)
