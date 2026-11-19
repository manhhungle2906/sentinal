"""Integration tests for the Ingestion API."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from sentinel.common.db import get_db
from sentinel.common.models import ApiSource, DetectorJob, SecurityEvent, Workspace
from sentinel.core.app import create_app as create_core_app
from sentinel.ingest.app import create_app as create_ingest_app


@pytest.fixture
def source(clean_db) -> ApiSource:
    """An API source with a known ingestion key."""
    from sentinel.common.security import generate_ingestion_key

    raw_key, prefix, digest = generate_ingestion_key()
    workspace = Workspace(name="Test workspace")
    clean_db.add(workspace)
    clean_db.flush()
    record = ApiSource(
        workspace_id=workspace.id,
        label="Test source",
        key_prefix=prefix,
        key_digest=digest,
    )
    clean_db.add(record)
    clean_db.commit()
    clean_db.refresh(record)
    record.raw_key = raw_key  # type: ignore[attr-defined]
    return record


@pytest.fixture
def ingest_client(clean_db) -> Iterator[TestClient]:
    app = create_ingest_app()

    def _override_get_db():
        yield clean_db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client


def _payload(**overrides) -> dict:
    payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "request",
        "source_ip": "203.0.113.10",
        "route_template": "/api/products",
        "method": "GET",
        "status_code": 200,
        "duration_ms": 12,
    }
    payload.update(overrides)
    return payload


def test_ingest_accepts_a_valid_event(ingest_client: TestClient, source: ApiSource, clean_db) -> None:
    response = ingest_client.post(
        "/ingest/v1/events",
        json=_payload(),
        headers={"X-Source-Key": source.raw_key},
    )
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "accepted"

    events = clean_db.execute(select(SecurityEvent)).scalars().all()
    assert len(events) == 1
    assert str(events[0].source_ip) == "203.0.113.10"


def test_ingest_requires_a_credential(ingest_client: TestClient) -> None:
    response = ingest_client.post("/ingest/v1/events", json=_payload())
    assert response.status_code == 401


def test_ingest_rejects_an_unknown_credential(ingest_client: TestClient) -> None:
    response = ingest_client.post(
        "/ingest/v1/events",
        json=_payload(),
        headers={"X-Source-Key": "sn_deadbeef.not-a-real-secret"},
    )
    assert response.status_code == 401


def test_identical_retry_returns_200_and_creates_no_second_event(
    ingest_client: TestClient, source: ApiSource, clean_db
) -> None:
    payload = _payload()
    first = ingest_client.post(
        "/ingest/v1/events", json=payload, headers={"X-Source-Key": source.raw_key}
    )
    assert first.status_code == 202

    retry = ingest_client.post(
        "/ingest/v1/events", json=payload, headers={"X-Source-Key": source.raw_key}
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == "duplicate"

    assert len(clean_db.execute(select(SecurityEvent)).scalars().all()) == 1
    assert len(clean_db.execute(select(DetectorJob)).scalars().all()) == 1


def test_same_event_id_with_different_content_returns_409(
    ingest_client: TestClient, source: ApiSource
) -> None:
    event_id = str(uuid.uuid4())
    first = ingest_client.post(
        "/ingest/v1/events",
        json=_payload(event_id=event_id, status_code=200),
        headers={"X-Source-Key": source.raw_key},
    )
    assert first.status_code == 202

    conflict = ingest_client.post(
        "/ingest/v1/events",
        json=_payload(event_id=event_id, status_code=500),
        headers={"X-Source-Key": source.raw_key},
    )
    assert conflict.status_code == 409


def test_invalid_payloads_are_rejected(
    ingest_client: TestClient, source: ApiSource
) -> None:
    cases = [
        _payload(event_type="exploit_attempt"),
        _payload(method="TRACE"),
        _payload(status_code=999),
        _payload(duration_ms=-1),
        _payload(route_template="/api/products?token=secret"),
        _payload(route_template="/api/products#fragment"),
        _payload(source_ip="not-an-ip"),
        _payload(event_id="not-a-uuid"),
    ]
    for payload in cases:
        response = ingest_client.post(
            "/ingest/v1/events", json=payload, headers={"X-Source-Key": source.raw_key}
        )
        assert response.status_code == 422, f"{payload} -> {response.status_code} {response.text}"


def test_a_naive_timestamp_is_rejected(ingest_client: TestClient, source: ApiSource) -> None:
    response = ingest_client.post(
        "/ingest/v1/events",
        json=_payload(occurred_at="2026-01-01T00:00:00"),
        headers={"X-Source-Key": source.raw_key},
    )
    assert response.status_code == 422


def test_extra_fields_are_rejected(ingest_client: TestClient, source: ApiSource) -> None:
    response = ingest_client.post(
        "/ingest/v1/events",
        json=_payload(authorization="Bearer leaked-token"),
        headers={"X-Source-Key": source.raw_key},
    )
    assert response.status_code == 422


def test_a_revoked_key_is_rejected(ingest_client: TestClient, source: ApiSource, clean_db) -> None:
    from sentinel.common.clock import utcnow

    source.revoked_at = utcnow()
    clean_db.commit()
    response = ingest_client.post(
        "/ingest/v1/events", json=_payload(), headers={"X-Source-Key": source.raw_key}
    )
    assert response.status_code == 401


def test_the_event_and_its_job_are_created_in_one_transaction(
    ingest_client: TestClient, source: ApiSource, clean_db
) -> None:
    ingest_client.post(
        "/ingest/v1/events", json=_payload(), headers={"X-Source-Key": source.raw_key}
    )
    event = clean_db.execute(select(SecurityEvent)).scalar_one()
    job = clean_db.execute(select(DetectorJob)).scalar_one()
    assert job.event_id == event.id
    assert job.status == "pending"


def test_ingest_health_endpoints(ingest_client: TestClient) -> None:
    live = ingest_client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["service"] == "ingest"

    ready = ingest_client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"


def test_core_and_ingest_expose_separate_health_services(clean_db) -> None:
    with TestClient(create_core_app()) as core_client:
        assert core_client.get("/health/live").json()["service"] == "core"
    with TestClient(create_ingest_app()) as ingest_client:
        assert ingest_client.get("/health/live").json()["service"] == "ingest"
