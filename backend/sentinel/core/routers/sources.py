"""API source management: create, list, rotate and revoke ingestion keys."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from sentinel.common.clock import utcnow
from sentinel.common.constants import ADMIN_ROLES
from sentinel.common.db import get_db
from sentinel.common.models import ApiSource
from sentinel.common.security import generate_ingestion_key
from sentinel.core.deps import (
    CurrentUser,
    WorkspaceContext,
    get_current_user,
    require_csrf,
    require_same_origin,
    workspace_dependency,
)

router = APIRouter(tags=["sources"])


class SourceCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    label: str = Field(min_length=1, max_length=120)


class SourceDto(BaseModel):
    id: str
    workspace_id: str
    label: str
    key_prefix: str
    created_at: datetime
    revoked_at: datetime | None
    is_active: bool


class SourceCreatedDto(SourceDto):
    """Creation response — the raw key is shown exactly once."""

    ingestion_key: str


@router.get("", response_model=list[SourceDto])
def list_sources(
    context: WorkspaceContext = Depends(workspace_dependency()),
    db: Session = Depends(get_db),
) -> list[SourceDto]:
    rows = db.execute(
        select(ApiSource)
        .where(ApiSource.workspace_id == context.workspace.id)
        .order_by(ApiSource.created_at.asc())
    ).scalars()
    return [
        SourceDto(
            id=str(row.id),
            workspace_id=str(row.workspace_id),
            label=row.label,
            key_prefix=row.key_prefix,
            created_at=row.created_at,
            revoked_at=row.revoked_at,
            is_active=row.revoked_at is None,
        )
        for row in rows
    ]


@router.post("", response_model=SourceCreatedDto, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: SourceCreateRequest,
    context: WorkspaceContext = Depends(workspace_dependency(ADMIN_ROLES)),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
    _origin: None = Depends(require_same_origin),
) -> SourceCreatedDto:
    raw_key, prefix, digest = generate_ingestion_key()
    source = ApiSource(
        workspace_id=context.workspace.id,
        label=payload.label,
        key_prefix=prefix,
        key_digest=digest,
        created_by=current.user.id,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return SourceCreatedDto(
        id=str(source.id),
        workspace_id=str(source.workspace_id),
        label=source.label,
        key_prefix=source.key_prefix,
        created_at=source.created_at,
        revoked_at=source.revoked_at,
        is_active=True,
        ingestion_key=raw_key,
    )


@router.post("/{source_id}/rotate", response_model=SourceCreatedDto)
def rotate_key(
    source_id: uuid.UUID,
    context: WorkspaceContext = Depends(workspace_dependency(ADMIN_ROLES)),
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
    _origin: None = Depends(require_same_origin),
) -> SourceCreatedDto:
    """Rotate the credential. The previous key stops working atomically."""
    source = db.execute(
        select(ApiSource).where(
            ApiSource.id == source_id, ApiSource.workspace_id == context.workspace.id
        )
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found")

    raw_key, prefix, digest = generate_ingestion_key()
    source.key_prefix = prefix
    source.key_digest = digest
    source.revoked_at = None
    db.commit()
    db.refresh(source)
    return SourceCreatedDto(
        id=str(source.id),
        workspace_id=str(source.workspace_id),
        label=source.label,
        key_prefix=source.key_prefix,
        created_at=source.created_at,
        revoked_at=source.revoked_at,
        is_active=True,
        ingestion_key=raw_key,
    )


@router.post("/{source_id}/revoke", response_model=SourceDto)
def revoke_key(
    source_id: uuid.UUID,
    context: WorkspaceContext = Depends(workspace_dependency(ADMIN_ROLES)),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
    _origin: None = Depends(require_same_origin),
) -> SourceDto:
    source = db.execute(
        select(ApiSource).where(
            ApiSource.id == source_id, ApiSource.workspace_id == context.workspace.id
        )
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found")
    source.revoked_at = utcnow()
    db.commit()
    db.refresh(source)
    return SourceDto(
        id=str(source.id),
        workspace_id=str(source.workspace_id),
        label=source.label,
        key_prefix=source.key_prefix,
        created_at=source.created_at,
        revoked_at=source.revoked_at,
        is_active=False,
    )
