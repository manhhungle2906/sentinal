"""Shared pytest fixtures.

Integration tests run against a real PostgreSQL database. The test database URL
is provided through ``SENTINEL_TEST_DATABASE_URL``; when it is absent the
PostgreSQL tests are skipped rather than silently passing.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from sentinel.common.models import Base

TEST_DATABASE_URL = os.environ.get("SENTINEL_TEST_DATABASE_URL")

requires_postgres = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="SENTINEL_TEST_DATABASE_URL is not configured",
)


@pytest.fixture(scope="session")
def engine() -> Iterator:
    if not TEST_DATABASE_URL:
        pytest.skip("SENTINEL_TEST_DATABASE_URL is not configured")
    eng = create_engine(TEST_DATABASE_URL, future=True)
    with eng.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def clean_db(engine) -> Iterator[Session]:
    """A session on a database truncated between tests."""
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE alerts, alert_evidence, alert_comments, "
                               "alert_history, detector_jobs, security_events, api_sources, "
                               "memberships, workspaces, sessions, users RESTART IDENTITY CASCADE"))
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def clock() -> Iterator:
    """A controllable clock for rule tests."""
    from sentinel.common.clock import fixed_clock

    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    yield fixed_clock(base)


@pytest.fixture
def base_time() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_event(
    *,
    source_id: uuid.UUID,
    source_ip: str = "203.0.113.10",
    received_at: datetime,
    ingest_seq: int,
    event_type: str = "request",
    status_code: int = 200,
    route_template: str = "/api/products",
    method: str = "GET",
    duration_ms: int | None = 12,
):
    """Build an unsaved SecurityEvent for rule tests."""
    from sentinel.common.models import SecurityEvent

    return SecurityEvent(
        id=uuid.uuid4(),
        source_id=source_id,
        event_uuid=uuid.uuid4(),
        received_at=received_at,
        request_at=received_at - timedelta(milliseconds=5),
        source_ip=source_ip,
        route_template=route_template,
        method=method,
        status_code=status_code,
        duration_ms=duration_ms,
        event_type=event_type,
        ingest_seq=ingest_seq,
    )
