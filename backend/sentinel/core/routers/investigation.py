"""Investigation APIs: alert detail, evidence, comments, history, status, assignment."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from sentinel.common.clock import utcnow
from sentinel.common.constants import (
    ALLOWED_STATUS_TRANSITIONS,
    INVESTIGATOR_ROLES,
    TERMINAL_ALERT_STATUSES,
    AlertStatus,
    WorkspaceRole,
)
from sentinel.common.db import get_db
from sentinel.common.models import (
    Alert,
    AlertComment,
    AlertEvidence,
    AlertHistory,
    Membership,
    SecurityEvent,
    User,
)
from sentinel.core.deps import (
    CurrentUser,
    WorkspaceContext,
    get_current_user,
    require_csrf,
    require_same_origin,
    workspace_dependency,
)

router = APIRouter(tags=["investigation"])


class EvidenceDto(BaseModel):
    event_id: str
    event_uuid: str
    received_at: datetime
    request_at: datetime | None
    source_ip: str
    route_template: str
    method: str
    status_code: int
    duration_ms: int | None
    event_type: str


class CommentDto(BaseModel):
    id: str
    author_id: str
    author_name: str
    body: str
    created_at: datetime


class HistoryDto(BaseModel):
    id: str
    action: str
    actor_id: str | None
    actor_name: str | None
    from_value: str | None
    to_value: str | None
    created_at: datetime


class AlertDetailDto(BaseModel):
    id: str
    workspace_id: str
    source_id: str
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
    resolved_at: datetime | None
    evidence: list[EvidenceDto]
    comments: list[CommentDto]
    history: list[HistoryDto]


class StatusUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    status: AlertStatus


class AssignRequest(BaseModel):
    assignee_id: uuid.UUID | None = None


class CommentCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(min_length=1, max_length=4000)


def _load_alert(db: Session, workspace_id: uuid.UUID, alert_id: uuid.UUID) -> Alert:
    alert = db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.workspace_id == workspace_id)
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert not found")
    return alert


def _evidence_rows(db: Session, alert: Alert) -> list[tuple[AlertEvidence, SecurityEvent]]:
    rows = db.execute(
        select(AlertEvidence, SecurityEvent)
        .join(SecurityEvent, SecurityEvent.id == AlertEvidence.event_id)
        .where(AlertEvidence.alert_id == alert.id)
        .order_by(SecurityEvent.received_at.asc(), SecurityEvent.id.asc())
    ).all()
    # Evidence must never cross the workspace/source boundary of the alert.
    return [(link, event) for link, event in rows if event.source_id == alert.source_id]


def _evidence_dto(event: SecurityEvent) -> EvidenceDto:
    return EvidenceDto(
        event_id=str(event.id),
        event_uuid=str(event.event_uuid),
        received_at=event.received_at,
        request_at=event.request_at,
        source_ip=str(event.source_ip),
        route_template=event.route_template,
        method=event.method,
        status_code=event.status_code,
        duration_ms=event.duration_ms,
        event_type=event.event_type,
    )


@router.get("/{alert_id}", response_model=AlertDetailDto)
def get_alert(
    alert_id: uuid.UUID,
    context: WorkspaceContext = Depends(workspace_dependency()),
    db: Session = Depends(get_db),
) -> AlertDetailDto:
    alert = _load_alert(db, context.workspace.id, alert_id)

    comment_rows = db.execute(
        select(AlertComment, User)
        .join(User, User.id == AlertComment.author_id)
        .where(AlertComment.alert_id == alert.id)
        .order_by(AlertComment.created_at.asc())
    ).all()

    history_rows = db.execute(
        select(AlertHistory, User)
        .outerjoin(User, User.id == AlertHistory.actor_id)
        .where(AlertHistory.alert_id == alert.id)
        .order_by(AlertHistory.created_at.asc())
    ).all()

    assignee = db.get(User, alert.assignee_id) if alert.assignee_id else None

    return AlertDetailDto(
        id=str(alert.id),
        workspace_id=str(alert.workspace_id),
        source_id=str(alert.source_id),
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
        assignee_name=assignee.display_name if assignee else None,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
        resolved_at=alert.resolved_at,
        evidence=[_evidence_dto(event) for _, event in _evidence_rows(db, alert)],
        comments=[
            CommentDto(
                id=str(comment.id),
                author_id=str(comment.author_id),
                author_name=author.display_name,
                body=comment.body,
                created_at=comment.created_at,
            )
            for comment, author in comment_rows
        ],
        history=[
            HistoryDto(
                id=str(entry.id),
                action=entry.action,
                actor_id=str(entry.actor_id) if entry.actor_id else None,
                actor_name=actor.display_name if actor else None,
                from_value=entry.from_value,
                to_value=entry.to_value,
                created_at=entry.created_at,
            )
            for entry, actor in history_rows
        ],
    )


@router.patch("/{alert_id}/status", response_model=AlertDetailDto)
def update_status(
    alert_id: uuid.UUID,
    payload: StatusUpdateRequest,
    context: WorkspaceContext = Depends(workspace_dependency(INVESTIGATOR_ROLES)),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
    _origin: None = Depends(require_same_origin),
) -> AlertDetailDto:
    alert = _load_alert(db, context.workspace.id, alert_id)
    if alert.status in TERMINAL_ALERT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="alert is in a terminal status and can no longer change",
        )
    allowed = ALLOWED_STATUS_TRANSITIONS.get(alert.status, set())
    if payload.status.value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"cannot move from {alert.status} to {payload.status.value}",
        )
    previous = alert.status
    alert.status = payload.status.value
    if payload.status.value in TERMINAL_ALERT_STATUSES:
        alert.resolved_at = utcnow()
    db.add(
        AlertHistory(
            alert_id=alert.id,
            actor_id=current.user.id,
            action="status_changed",
            from_value=previous,
            to_value=payload.status.value,
        )
    )
    db.commit()
    return get_alert(alert_id, context, db)


@router.patch("/{alert_id}/assignee", response_model=AlertDetailDto)
def update_assignee(
    alert_id: uuid.UUID,
    payload: AssignRequest,
    context: WorkspaceContext = Depends(workspace_dependency(INVESTIGATOR_ROLES)),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
    _origin: None = Depends(require_same_origin),
) -> AlertDetailDto:
    alert = _load_alert(db, context.workspace.id, alert_id)
    previous = str(alert.assignee_id) if alert.assignee_id else None

    if payload.assignee_id is None:
        alert.assignee_id = None
        to_value = None
    else:
        membership = db.execute(
            select(Membership).where(
                Membership.workspace_id == context.workspace.id,
                Membership.user_id == payload.assignee_id,
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="assignee is not a member of this workspace",
            )
        if membership.role not in INVESTIGATOR_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="alerts can only be assigned to an owner or analyst",
            )
        alert.assignee_id = payload.assignee_id
        to_value = str(payload.assignee_id)

    db.add(
        AlertHistory(
            alert_id=alert.id,
            actor_id=current.user.id,
            action="assignee_changed",
            from_value=previous,
            to_value=to_value,
        )
    )
    db.commit()
    return get_alert(alert_id, context, db)


@router.post("/{alert_id}/comments", response_model=CommentDto, status_code=status.HTTP_201_CREATED)
def add_comment(
    alert_id: uuid.UUID,
    payload: CommentCreateRequest,
    context: WorkspaceContext = Depends(workspace_dependency(INVESTIGATOR_ROLES)),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
    _origin: None = Depends(require_same_origin),
) -> CommentDto:
    alert = _load_alert(db, context.workspace.id, alert_id)
    comment = AlertComment(
        alert_id=alert.id,
        author_id=current.user.id,
        body=payload.body,
    )
    db.add(comment)
    db.add(
        AlertHistory(
            alert_id=alert.id,
            actor_id=current.user.id,
            action="commented",
            to_value=None,
        )
    )
    db.commit()
    db.refresh(comment)
    return CommentDto(
        id=str(comment.id),
        author_id=str(comment.author_id),
        author_name=current.user.display_name,
        body=comment.body,
        created_at=comment.created_at,
    )


@router.get("/{alert_id}/history", response_model=list[HistoryDto])
def get_history(
    alert_id: uuid.UUID,
    context: WorkspaceContext = Depends(workspace_dependency()),
    db: Session = Depends(get_db),
) -> list[HistoryDto]:
    alert = _load_alert(db, context.workspace.id, alert_id)
    rows = db.execute(
        select(AlertHistory, User)
        .outerjoin(User, User.id == AlertHistory.actor_id)
        .where(AlertHistory.alert_id == alert.id)
        .order_by(AlertHistory.created_at.asc())
    ).all()
    return [
        HistoryDto(
            id=str(entry.id),
            action=entry.action,
            actor_id=str(entry.actor_id) if entry.actor_id else None,
            actor_name=actor.display_name if actor else None,
            from_value=entry.from_value,
            to_value=entry.to_value,
            created_at=entry.created_at,
        )
        for entry, actor in rows
    ]


@router.get("/{alert_id}/evidence", response_model=list[EvidenceDto])
def get_evidence(
    alert_id: uuid.UUID,
    context: WorkspaceContext = Depends(workspace_dependency()),
    db: Session = Depends(get_db),
) -> list[EvidenceDto]:
    alert = _load_alert(db, context.workspace.id, alert_id)
    return [_evidence_dto(event) for _, event in _evidence_rows(db, alert)]


@router.delete("/{alert_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_own_comment(
    alert_id: uuid.UUID,
    comment_id: uuid.UUID,
    context: WorkspaceContext = Depends(workspace_dependency(INVESTIGATOR_ROLES)),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
    _origin: None = Depends(require_same_origin),
) -> Response:
    alert = _load_alert(db, context.workspace.id, alert_id)
    comment = db.execute(
        select(AlertComment).where(AlertComment.id == comment_id, AlertComment.alert_id == alert.id)
    ).scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="comment not found")
    if comment.author_id != current.user.id and context.role != WorkspaceRole.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="only the author or an owner can delete"
        )
    db.delete(comment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
