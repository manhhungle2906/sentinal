"""Authentication routes: register, login, logout, me."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sentinel.common.clock import utcnow
from sentinel.common.config import Settings, get_settings
from sentinel.common.db import get_db
from sentinel.common.models import Session as SessionModel
from sentinel.common.models import User
from sentinel.common.rate_limit import SlidingWindowRateLimiter
from sentinel.common.security import generate_token, hash_password, token_digest, verify_password
from sentinel.core.deps import CurrentUser, get_current_user, require_csrf, require_same_origin

router = APIRouter(tags=["auth"])

_login_limiter = SlidingWindowRateLimiter(limit=10, window_seconds=60)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    display_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserDto(BaseModel):
    id: str
    email: str
    display_name: str
    created_at: datetime


class SessionDto(BaseModel):
    user: UserDto
    expires_at: datetime


def _user_dto(user: User) -> UserDto:
    return UserDto(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        created_at=user.created_at,
    )


def _issue_session(db: Session, user: User, response: Response, settings: Settings) -> SessionModel:
    raw_token = generate_token()
    csrf_token = generate_token()
    record = SessionModel(
        user_id=user.id,
        token_digest=token_digest(raw_token),
        csrf_token_digest=token_digest(csrf_token),
        expires_at=utcnow() + timedelta(seconds=settings.session_ttl_seconds),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        samesite="lax",
        secure=settings.secure_cookies,
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    return record


@router.post("/register", response_model=SessionDto, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SessionDto:
    email = payload.email.lower()
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="an account with this email exists"
        )
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="an account with this email exists"
        ) from exc
    db.refresh(user)
    record = _issue_session(db, user, response, settings)
    return SessionDto(user=_user_dto(user), expires_at=record.expires_at)


@router.post("/login", response_model=SessionDto)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SessionDto:
    client_key = request.client.host if request.client else "unknown"
    allowed, _ = _login_limiter.check(client_key, utcnow())
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many login attempts, retry later",
        )

    email = payload.email.lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    # Same error for unknown user and wrong password.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid email or password"
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account is disabled")
    record = _issue_session(db, user, response, settings)
    return SessionDto(user=_user_dto(user), expires_at=record.expires_at)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _csrf: None = Depends(require_csrf),
    _origin: None = Depends(require_same_origin),
) -> Response:
    record = current.session
    record.revoked_at = datetime.now(UTC)
    db.commit()
    response.status_code = status.HTTP_204_NO_CONTENT
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
    return response


@router.get("/me", response_model=UserDto)
def me(current: CurrentUser = Depends(get_current_user)) -> UserDto:
    return _user_dto(current.user)
