"""Workspace and membership routes."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sentinel.common.constants import ADMIN_ROLES, WorkspaceRole
from sentinel.common.db import get_db
from sentinel.common.models import Membership, User, Workspace
from sentinel.core.deps import (
    CurrentUser,
    WorkspaceContext,
    get_current_user,
    require_csrf,
    require_same_origin,
    workspace_dependency,
)

router = APIRouter(tags=["workspaces"])


class WorkspaceCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)


class WorkspaceDto(BaseModel):
    id: str
    name: str
    role: str
    created_at: datetime


class MemberAddRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    role: WorkspaceRole = WorkspaceRole.ANALYST


class MemberDto(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: str
    joined_at: datetime


@router.get("", response_model=list[WorkspaceDto])
def list_workspaces(
    current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[WorkspaceDto]:
    rows = db.execute(
        select(Workspace, Membership)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == current.user.id)
        .order_by(Workspace.created_at.asc())
    ).all()
    return [
        WorkspaceDto(
            id=str(workspace.id),
            name=workspace.name,
            role=membership.role,
            created_at=workspace.created_at,
        )
        for workspace, membership in rows
    ]


@router.post("", response_model=WorkspaceDto, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreateRequest,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
    _origin: None = Depends(require_same_origin),
) -> WorkspaceDto:
    workspace = Workspace(name=payload.name, created_by=current.user.id)
    db.add(workspace)
    db.flush()
    db.add(
        Membership(
            workspace_id=workspace.id, user_id=current.user.id, role=WorkspaceRole.OWNER.value
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="workspace could not be created"
        ) from exc
    db.refresh(workspace)
    return WorkspaceDto(
        id=str(workspace.id),
        name=workspace.name,
        role=WorkspaceRole.OWNER.value,
        created_at=workspace.created_at,
    )


@router.get("/{workspace_id}/members", response_model=list[MemberDto])
def list_members(
    workspace_id: uuid.UUID,
    context: WorkspaceContext = Depends(workspace_dependency()),
    db: Session = Depends(get_db),
) -> list[MemberDto]:
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == workspace_id)
        .order_by(Membership.created_at.asc())
    ).all()
    return [
        MemberDto(
            user_id=str(membership.user_id),
            email=user.email,
            display_name=user.display_name,
            role=membership.role,
            joined_at=membership.created_at,
        )
        for membership, user in rows
    ]


@router.post(
    "/{workspace_id}/members",
    response_model=MemberDto,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    workspace_id: uuid.UUID,
    payload: MemberAddRequest,
    context: WorkspaceContext = Depends(workspace_dependency(ADMIN_ROLES)),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
    _origin: None = Depends(require_same_origin),
) -> MemberDto:
    if payload.role == WorkspaceRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="owner role cannot be granted through this endpoint",
        )
    email = payload.email.lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no account exists with this email"
        )
    existing = db.execute(
        select(Membership).where(
            Membership.workspace_id == workspace_id, Membership.user_id == user.id
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="user is already a member")
    membership = Membership(workspace_id=workspace_id, user_id=user.id, role=payload.role.value)
    db.add(membership)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="user is already a member"
        ) from exc
    db.refresh(membership)
    return MemberDto(
        user_id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        role=membership.role,
        joined_at=membership.created_at,
    )


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    context: WorkspaceContext = Depends(workspace_dependency(ADMIN_ROLES)),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
    _origin: None = Depends(require_same_origin),
) -> Response:
    membership = db.execute(
        select(Membership).where(
            Membership.workspace_id == workspace_id, Membership.user_id == user_id
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="member not found")
    if membership.role == WorkspaceRole.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="the workspace owner cannot be removed"
        )
    db.delete(membership)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
