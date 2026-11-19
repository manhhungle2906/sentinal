"""Request dependencies: session resolution, CSRF and workspace authorization."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from sentinel.common.config import Settings, get_settings
from sentinel.common.db import get_db
from sentinel.common.models import Membership, User, Workspace
from sentinel.common.models import Session as SessionModel
from sentinel.common.security import token_digest

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class CurrentUser:
    user: User
    session: SessionModel


@dataclass(frozen=True)
class WorkspaceContext:
    workspace: Workspace
    membership: Membership
    role: str


def _get_session_record(db: Session, raw_token: str) -> SessionModel | None:
    digest = token_digest(raw_token)
    record = db.execute(
        select(SessionModel).where(SessionModel.token_digest == digest)
    ).scalar_one_or_none()
    if record is None:
        return None
    if record.revoked_at is not None:
        return None
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return None
    return record


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    """Resolve the session cookie into an authenticated user.

    Missing or invalid session -> 401.
    """
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    record = _get_session_record(db, raw_token)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired session"
        )
    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired session"
        )
    return CurrentUser(user=user, session=record)


def require_csrf(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """Enforce CSRF protection on state-changing browser requests.

    The browser sends the CSRF token in a readable cookie and echoes it in the
    ``X-CSRF-Token`` header; the stored digest must match the session digest.
    """
    if request.method in SAFE_METHODS:
        return
    header_token = request.headers.get("x-csrf-token")
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    if not header_token or not cookie_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="missing CSRF token")
    if token_digest(header_token) != token_digest(cookie_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid CSRF token")


def require_same_origin(request: Request) -> None:
    """Reject state-changing requests that do not come from the app origin."""
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin is None:
        # Non-browser clients (curl, tests) omit Origin; the CSRF token still
        # applies, so this is not a security hole.
        return
    host = request.headers.get("host")
    if host and origin.split("://")[-1] != host:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="cross-origin request rejected"
        )


def resolve_workspace(
    workspace_id: uuid.UUID,
    db: Session,
    user: User,
    allowed_roles: set[str] | None = None,
) -> WorkspaceContext:
    """Load a workspace and verify the current user may access it.

    - Not a member -> 404 (the object is inaccessible to this user).
    - Member with a disallowed role -> 403.
    """
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")
    membership = db.execute(
        select(Membership).where(
            Membership.workspace_id == workspace_id, Membership.user_id == user.id
        )
    ).scalar_one_or_none()
    if membership is None:
        # Do not leak the existence of a foreign workspace.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")
    if allowed_roles is not None and membership.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="insufficient role for this action",
        )
    return WorkspaceContext(workspace=workspace, membership=membership, role=membership.role)


def workspace_dependency(
    allowed_roles: set[str] | None = None,
) -> Callable[..., WorkspaceContext]:
    """Build a dependency that resolves the ``X-Workspace-Id`` header."""

    def _dependency(
        request: Request,
        current: CurrentUser = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> WorkspaceContext:
        # The workspace id comes from the path when the route has one,
        # otherwise from the X-Workspace-Id header.
        raw = request.path_params.get("workspace_id") or request.headers.get(
            "x-workspace-id"
        )
        if not raw:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="X-Workspace-Id header required"
            )
        try:
            workspace_id = uuid.UUID(str(raw))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="invalid workspace id"
            ) from exc
        return resolve_workspace(workspace_id, db, current.user, allowed_roles)

    return _dependency
