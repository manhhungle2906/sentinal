"""Shared persistence models for API Sentinel.

All services (Core, Ingest, Detector) share one PostgreSQL database. The models
here are the single source of truth for the schema; Alembic owns migrations.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    cast,
    func,
    literal,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.schema import Identity


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def inet_equals(column, value: str):
    """Compare an INET column with a string value.

    PostgreSQL has no implicit ``inet = varchar`` operator, so the value is
    cast explicitly instead of relying on the driver.
    """
    return column == cast(literal(value), INET)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    memberships: Mapped[list[Membership]] = relationship(back_populates="user")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------
class Workspace(Base, TimestampMixin):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_membership_workspace_user"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # owner | analyst | viewer
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    workspace: Mapped[Workspace] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


# ---------------------------------------------------------------------------
# API source + ingestion credential
# ---------------------------------------------------------------------------
class ApiSource(Base, TimestampMixin):
    __tablename__ = "api_sources"

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    key_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    workspace: Mapped[Workspace] = relationship()


# ---------------------------------------------------------------------------
# Security events
# ---------------------------------------------------------------------------
class SecurityEvent(Base):
    __tablename__ = "security_events"
    __table_args__ = (
        UniqueConstraint("source_id", "event_uuid", name="uq_event_source_uuid"),
        Index("ix_event_source_received", "source_id", "received_at"),
        Index("ix_event_source_ip_received", "source_id", "source_ip", "received_at"),
        Index("ix_event_received_seq", "received_at", "ingest_seq"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Monotonic ingestion sequence: stable ordering for rows that share a
    # receipt timestamp.
    ingest_seq: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=False),
        unique=True,
        autoincrement=True,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_sources.id", ondelete="CASCADE"), nullable=False
    )
    event_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    request_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_ip: Mapped[str] = mapped_column(INET, nullable=False)
    route_template: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, default="request")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Detector jobs
# ---------------------------------------------------------------------------
class DetectorJob(Base):
    __tablename__ = "detector_jobs"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_job_event"),
        Index("ix_job_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("security_events.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    event: Mapped[SecurityEvent] = relationship()


# ---------------------------------------------------------------------------
# Alerts, evidence, comments, history
# ---------------------------------------------------------------------------
class Alert(Base, TimestampMixin):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("rule_key", "trigger_event_id", name="uq_alert_rule_trigger_event"),
        Index("ix_alert_workspace_created", "workspace_id", "created_at"),
        Index("ix_alert_workspace_status", "workspace_id", "status"),
        Index("ix_alert_workspace_severity", "workspace_id", "severity"),
        Index("ix_alert_workspace_source", "workspace_id", "source_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_sources.id", ondelete="CASCADE"), nullable=False
    )
    rule_key: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    source_ip: Mapped[str] = mapped_column(INET, nullable=False)

    # Frozen snapshot of the trigger moment.
    count_at_trigger: Mapped[int] = mapped_column(Integer, nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    trigger_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("security_events.id", ondelete="CASCADE"), nullable=False
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    suppressed_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    evidence: Mapped[list[AlertEvidence]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )


class AlertEvidence(Base):
    __tablename__ = "alert_evidence"
    __table_args__ = (UniqueConstraint("alert_id", "event_id", name="uq_evidence_alert_event"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("security_events.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    alert: Mapped[Alert] = relationship(back_populates="evidence")
    event: Mapped[SecurityEvent] = relationship()


class AlertComment(Base):
    __tablename__ = "alert_comments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    author: Mapped[User] = relationship()


class AlertHistory(Base):
    __tablename__ = "alert_history"

    id: Mapped[uuid.UUID] = _uuid_pk()
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    from_value: Mapped[str | None] = mapped_column(String(255))
    to_value: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Worker heartbeat
# ---------------------------------------------------------------------------
class DetectorHeartbeat(Base):
    __tablename__ = "detector_heartbeat"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
