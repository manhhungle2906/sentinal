"""Monitoring read APIs: events, dashboard statistics and alert listing."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sentinel.common.constants import ALLOWED_EVENT_TYPES, ALLOWED_METHODS, AlertStatus
from sentinel.common.db import get_db
from sentinel.common.models import Alert, AlertEvidence, ApiSource, SecurityEvent, User, inet_equals
from sentinel.core.deps import WorkspaceContext, workspace_dependency

router = APIRouter(tags=["monitoring"])

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50
# Fixed bucket granularity for the traffic chart (documented in README).
DASHBOARD_BUCKET_SECONDS = 60


class EventDto(BaseModel):
    id: str
    event_uuid: str
    source_id: str
    source_label: str | None
    received_at: datetime
    request_at: datetime | None
    source_ip: str
    route_template: str
    method: str
    status_code: int
    duration_ms: int | None
    event_type: str


class EventPageDto(BaseModel):
    items: list[EventDto]
    total: int
    limit: int
    offset: int


class TrafficBucketDto(BaseModel):
    bucket_start: datetime
    total_requests: int
    failed_logins: int
    access_denials: int


class DashboardStatsDto(BaseModel):
    source_id: str | None
    range_start: datetime
    range_end: datetime
    total_requests: int
    failed_logins: int
    access_denials: int
    open_alerts: int
    total_alerts: int
    bucket_seconds: int
    traffic: list[TrafficBucketDto]


class AlertSummaryDto(BaseModel):
    id: str
    workspace_id: str
    source_id: str
    source_label: str | None
    rule_key: str
    severity: str
    status: str
    source_ip: str
    count_at_trigger: int
    threshold: int
    window_seconds: int
    interval_start: datetime
    interval_end: datetime
    assignee_id: str | None
    assignee_name: str | None
    created_at: datetime
    updated_at: datetime
    evidence_count: int


class AlertPageDto(BaseModel):
    items: list[AlertSummaryDto]
    total: int
    limit: int
    offset: int


def _parse_range(
    start: datetime | None, end: datetime | None, default_minutes: int = 60
) -> tuple[datetime, datetime]:
    end_value = end or datetime.now(UTC)
    start_value = start or (end_value - timedelta(minutes=default_minutes))
    if start_value.tzinfo is None:
        start_value = start_value.replace(tzinfo=UTC)
    if end_value.tzinfo is None:
        end_value = end_value.replace(tzinfo=UTC)
    if start_value > end_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="start must not be after end"
        )
    return start_value, end_value


def _source_ids_for_workspace(db: Session, workspace_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        db.execute(select(ApiSource.id).where(ApiSource.workspace_id == workspace_id)).scalars()
    )


def _resolve_source(
    db: Session, workspace_id: uuid.UUID, source_id: uuid.UUID | None
) -> uuid.UUID | None:
    if source_id is None:
        return None
    source = db.execute(
        select(ApiSource).where(ApiSource.id == source_id, ApiSource.workspace_id == workspace_id)
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found")
    return source.id


@router.get("/events", response_model=EventPageDto)
def list_events(
    context: WorkspaceContext = Depends(workspace_dependency()),
    db: Session = Depends(get_db),
    start: datetime | None = None,
    end: datetime | None = None,
    source_id: uuid.UUID | None = None,
    source_ip: str | None = None,
    route_template: str | None = None,
    method: str | None = None,
    status_code: int | None = Query(default=None, ge=100, le=599),
    event_type: str | None = None,
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> EventPageDto:
    start_value, end_value = _parse_range(start, end)
    if method is not None and method.upper() not in ALLOWED_METHODS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="method is not allowed")
    if event_type is not None and event_type not in ALLOWED_EVENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="event_type is not recognized"
        )

    source_ids = _source_ids_for_workspace(db, context.workspace.id)
    if not source_ids:
        return EventPageDto(items=[], total=0, limit=limit, offset=offset)

    filters = [
        SecurityEvent.source_id.in_(source_ids),
        SecurityEvent.received_at >= start_value,
        SecurityEvent.received_at <= end_value,
    ]
    if source_id is not None:
        filters.append(SecurityEvent.source_id == source_id)
    if source_ip:
        filters.append(inet_equals(SecurityEvent.source_ip, source_ip))
    if route_template:
        filters.append(SecurityEvent.route_template == route_template)
    if method:
        filters.append(SecurityEvent.method == method.upper())
    if status_code is not None:
        filters.append(SecurityEvent.status_code == status_code)
    if event_type:
        filters.append(SecurityEvent.event_type == event_type)

    total = db.execute(select(func.count()).select_from(SecurityEvent).where(*filters)).scalar_one()
    rows = db.execute(
        select(SecurityEvent, ApiSource.label)
        .outerjoin(ApiSource, ApiSource.id == SecurityEvent.source_id)
        .where(*filters)
        .order_by(SecurityEvent.received_at.desc(), SecurityEvent.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return EventPageDto(
        items=[
            EventDto(
                id=str(event.id),
                event_uuid=str(event.event_uuid),
                source_id=str(event.source_id),
                source_label=label,
                received_at=event.received_at,
                request_at=event.request_at,
                source_ip=str(event.source_ip),
                route_template=event.route_template,
                method=event.method,
                status_code=event.status_code,
                duration_ms=event.duration_ms,
                event_type=event.event_type,
            )
            for event, label in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/dashboard/stats", response_model=DashboardStatsDto)
def dashboard_stats(
    context: WorkspaceContext = Depends(workspace_dependency()),
    db: Session = Depends(get_db),
    start: datetime | None = None,
    end: datetime | None = None,
    source_id: uuid.UUID | None = None,
) -> DashboardStatsDto:
    start_value, end_value = _parse_range(start, end)
    source_ids = _source_ids_for_workspace(db, context.workspace.id)
    resolved_source = _resolve_source(db, context.workspace.id, source_id)

    event_source_ids = [resolved_source] if resolved_source is not None else source_ids

    def _count(extra_filters: list) -> int:
        if not event_source_ids:
            return 0
        filters = [
            SecurityEvent.source_id.in_(event_source_ids),
            SecurityEvent.received_at >= start_value,
            SecurityEvent.received_at <= end_value,
            *extra_filters,
        ]
        return db.execute(
            select(func.count()).select_from(SecurityEvent).where(*filters)
        ).scalar_one()

    total_requests = _count([])
    failed_logins = _count([SecurityEvent.event_type == "login_failed"])
    access_denials = _count(
        [
            SecurityEvent.status_code.in_([401, 403]),
            SecurityEvent.event_type != "login_failed",
        ]
    )

    alert_filters = [
        Alert.workspace_id == context.workspace.id,
        Alert.created_at <= end_value,
    ]
    if resolved_source is not None:
        alert_filters.append(Alert.source_id == resolved_source)
    total_alerts = db.execute(
        select(func.count()).select_from(Alert).where(*alert_filters)
    ).scalar_one()
    open_alerts = db.execute(
        select(func.count())
        .select_from(Alert)
        .where(
            *alert_filters,
            Alert.status.in_([AlertStatus.NEW.value, AlertStatus.INVESTIGATING.value]),
        )
    ).scalar_one()

    traffic = _traffic_buckets(
        db, event_source_ids, start_value, end_value, DASHBOARD_BUCKET_SECONDS
    )

    return DashboardStatsDto(
        source_id=str(resolved_source) if resolved_source else None,
        range_start=start_value,
        range_end=end_value,
        total_requests=total_requests,
        failed_logins=failed_logins,
        access_denials=access_denials,
        open_alerts=open_alerts,
        total_alerts=total_alerts,
        bucket_seconds=DASHBOARD_BUCKET_SECONDS,
        traffic=traffic,
    )


def _traffic_buckets(
    db: Session,
    source_ids: list[uuid.UUID],
    start: datetime,
    end: datetime,
    bucket_seconds: int,
) -> list[TrafficBucketDto]:
    """Zero-filled traffic buckets over the requested range."""
    bucket = (
        func.floor(func.extract("epoch", SecurityEvent.received_at) / bucket_seconds)
        * bucket_seconds
    )
    rows = []
    if source_ids:
        rows = db.execute(
            select(
                bucket.label("bucket"),
                func.count().label("total"),
                func.count().filter(SecurityEvent.event_type == "login_failed").label("logins"),
                func.count()
                .filter(
                    SecurityEvent.status_code.in_([401, 403]),
                    SecurityEvent.event_type != "login_failed",
                )
                .label("denials"),
            )
            .where(
                SecurityEvent.source_id.in_(source_ids),
                SecurityEvent.received_at >= start,
                SecurityEvent.received_at <= end,
            )
            .group_by("bucket")
            .order_by("bucket")
        ).all()

    by_bucket = {
        int(row.bucket): (int(row.total), int(row.logins), int(row.denials)) for row in rows
    }
    first = int(start.timestamp()) // bucket_seconds * bucket_seconds
    last = int(end.timestamp()) // bucket_seconds * bucket_seconds
    result: list[TrafficBucketDto] = []
    current = first
    while current <= last:
        total, logins, denials = by_bucket.get(current, (0, 0, 0))
        result.append(
            TrafficBucketDto(
                bucket_start=datetime.fromtimestamp(current, tz=UTC),
                total_requests=total,
                failed_logins=logins,
                access_denials=denials,
            )
        )
        current += bucket_seconds
    return result


@router.get("/alerts", response_model=AlertPageDto)
def list_alerts(
    context: WorkspaceContext = Depends(workspace_dependency()),
    db: Session = Depends(get_db),
    status_filter: Literal["new", "investigating", "resolved", "false_positive"] | None = None,
    severity: str | None = None,
    source_id: uuid.UUID | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> AlertPageDto:
    filters = [Alert.workspace_id == context.workspace.id]
    if status_filter:
        filters.append(Alert.status == status_filter)
    if severity:
        filters.append(Alert.severity == severity)
    if source_id is not None:
        filters.append(Alert.source_id == source_id)
    if start is not None or end is not None:
        start_value, end_value = _parse_range(start, end)
        filters.append(Alert.created_at >= start_value)
        filters.append(Alert.created_at <= end_value)

    total = db.execute(select(func.count()).select_from(Alert).where(*filters)).scalar_one()
    rows = db.execute(
        select(Alert, ApiSource.label, func.count(AlertEvidence.id), User.display_name)
        .outerjoin(ApiSource, ApiSource.id == Alert.source_id)
        .outerjoin(AlertEvidence, AlertEvidence.alert_id == Alert.id)
        .outerjoin(User, User.id == Alert.assignee_id)
        .where(*filters)
        .group_by(Alert.id, ApiSource.label, User.display_name)
        .order_by(Alert.created_at.desc(), Alert.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return AlertPageDto(
        items=[
            AlertSummaryDto(
                id=str(alert.id),
                workspace_id=str(alert.workspace_id),
                source_id=str(alert.source_id),
                source_label=label,
                rule_key=alert.rule_key,
                severity=alert.severity,
                status=alert.status,
                source_ip=str(alert.source_ip),
                count_at_trigger=alert.count_at_trigger,
                threshold=alert.threshold,
                window_seconds=alert.window_seconds,
                interval_start=alert.interval_start,
                interval_end=alert.interval_end,
                assignee_id=str(alert.assignee_id) if alert.assignee_id else None,
                assignee_name=assignee_name,
                created_at=alert.created_at,
                updated_at=alert.updated_at,
                evidence_count=int(evidence_count),
            )
            for alert, label, evidence_count, assignee_name in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
