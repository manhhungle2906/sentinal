"""Integration tests for the detection worker.

The worker is driven directly against the test database so the tests never
wait on a real detection window.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sentinel.common.models import (
    Alert,
    AlertEvidence,
    DetectorJob,
    SecurityEvent,
)
from sentinel.detector.worker import Detector
from sqlalchemy import select


@pytest.fixture
def detector_source(clean_db):
    from sentinel.common.models import ApiSource, Workspace

    workspace = Workspace(name="Detection workspace")
    clean_db.add(workspace)
    clean_db.flush()
    source = ApiSource(
        workspace_id=workspace.id,
        label="Detector source",
        key_prefix="sn_test01",
        key_digest="digest-for-detector-tests",
    )
    clean_db.add(source)
    clean_db.commit()
    clean_db.refresh(source)
    return source


def _persist_event(
    db,
    source,
    *,
    source_ip: str = "203.0.113.10",
    event_type: str = "request",
    status_code: int = 200,
    received_at=None,
):
    """Persist an event and its detection job, as the ingestion API would."""
    from sentinel.common.clock import utcnow

    moment = received_at or utcnow()
    event = SecurityEvent(
        source_id=source.id,
        event_uuid=uuid.uuid4(),
        received_at=moment,
        request_at=moment,
        source_ip=source_ip,
        route_template="/api/products",
        method="GET",
        status_code=status_code,
        duration_ms=10,
        event_type=event_type,
    )
    db.add(event)
    db.flush()
    db.add(DetectorJob(event_id=event.id, status="pending"))
    db.commit()
    db.refresh(event)
    return event


def _run_detector(clean_db, monkeypatch) -> None:
    """Run one detector batch against the test database."""
    import sentinel.detector.worker as worker_module

    class _Session:
        def __init__(self) -> None:
            self._session = clean_db

        def __getattr__(self, name):
            return getattr(self._session, name)

    monkeypatch.setattr(worker_module, "SessionLocal", lambda: _Session())
    detector = Detector()
    detector.run_once()


def test_a_crossing_creates_an_alert_with_evidence(clean_db, detector_source, monkeypatch) -> None:
    from sentinel.common.clock import utcnow

    base = utcnow()
    for index in range(5):
        _persist_event(
            clean_db,
            detector_source,
            event_type="login_failed",
            status_code=401,
            received_at=base + timedelta(seconds=index),
        )

    _run_detector(clean_db, monkeypatch)

    alerts = clean_db.execute(select(Alert)).scalars().all()
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.rule_key == "failed_login_burst"
    assert alert.severity == "high"
    assert alert.count_at_trigger == 5
    assert alert.threshold == 5
    assert alert.window_seconds == 120
    assert alert.status == "new"
    assert str(alert.source_ip) == "203.0.113.10"

    evidence = (
        clean_db.execute(select(AlertEvidence).where(AlertEvidence.alert_id == alert.id))
        .scalars()
        .all()
    )
    assert len(evidence) == 5


def test_the_worker_marks_the_jobs_as_done(clean_db, detector_source, monkeypatch) -> None:
    from sentinel.common.clock import utcnow

    _persist_event(clean_db, detector_source, received_at=utcnow())
    _run_detector(clean_db, monkeypatch)

    jobs = clean_db.execute(select(DetectorJob)).scalars().all()
    assert jobs[0].status == "done"


def test_below_threshold_creates_no_alert(clean_db, detector_source, monkeypatch) -> None:
    from sentinel.common.clock import utcnow

    base = utcnow()
    for index in range(4):
        _persist_event(
            clean_db,
            detector_source,
            event_type="login_failed",
            status_code=401,
            received_at=base + timedelta(seconds=index),
        )

    _run_detector(clean_db, monkeypatch)
    assert clean_db.execute(select(Alert)).scalars().all() == []


def test_a_repeated_run_does_not_duplicate_the_alert(
    clean_db, detector_source, monkeypatch
) -> None:
    from sentinel.common.clock import utcnow

    base = utcnow()
    for index in range(5):
        _persist_event(
            clean_db,
            detector_source,
            event_type="login_failed",
            status_code=401,
            received_at=base + timedelta(seconds=index),
        )

    _run_detector(clean_db, monkeypatch)
    _run_detector(clean_db, monkeypatch)

    alerts = clean_db.execute(select(Alert)).scalars().all()
    assert len(alerts) == 1


def test_a_crossing_during_suppression_does_not_create_a_second_alert(
    clean_db, detector_source, monkeypatch
) -> None:
    from sentinel.common.clock import utcnow

    base = utcnow()
    # First burst crosses the threshold.
    for index in range(5):
        _persist_event(
            clean_db,
            detector_source,
            event_type="login_failed",
            status_code=401,
            received_at=base + timedelta(seconds=index),
        )
    _run_detector(clean_db, monkeypatch)
    assert len(clean_db.execute(select(Alert)).scalars().all()) == 1

    # A second burst inside the 120 second suppression window.
    for index in range(5):
        _persist_event(
            clean_db,
            detector_source,
            event_type="login_failed",
            status_code=401,
            received_at=base + timedelta(seconds=30 + index),
        )
    _run_detector(clean_db, monkeypatch)
    assert len(clean_db.execute(select(Alert)).scalars().all()) == 1


def test_a_fresh_crossing_after_the_suppression_window_creates_a_new_alert(
    clean_db, detector_source, monkeypatch
) -> None:
    from sentinel.common.clock import utcnow

    base = utcnow()
    for index in range(5):
        _persist_event(
            clean_db,
            detector_source,
            event_type="login_failed",
            status_code=401,
            received_at=base + timedelta(seconds=index),
        )
    _run_detector(clean_db, monkeypatch)
    assert len(clean_db.execute(select(Alert)).scalars().all()) == 1

    # A burst well after the suppression window expires.
    later = base + timedelta(seconds=200)
    for index in range(5):
        _persist_event(
            clean_db,
            detector_source,
            event_type="login_failed",
            status_code=401,
            received_at=later + timedelta(seconds=index),
        )
    _run_detector(clean_db, monkeypatch)
    assert len(clean_db.execute(select(Alert)).scalars().all()) == 2


def test_events_from_another_ip_do_not_contribute(clean_db, detector_source, monkeypatch) -> None:
    """Counting is separated per source IP: another IP never adds to the count.

    Four failures from a neighbouring IP plus one from the trigger IP stay
    below the threshold of five, so no alert is raised.
    """
    from sentinel.common.clock import utcnow

    base = utcnow()
    for index in range(4):
        _persist_event(
            clean_db,
            detector_source,
            source_ip="198.51.100.7",
            event_type="login_failed",
            status_code=401,
            received_at=base + timedelta(seconds=index),
        )
    _persist_event(
        clean_db,
        detector_source,
        source_ip="203.0.113.99",
        event_type="login_failed",
        status_code=401,
        received_at=base + timedelta(seconds=10),
    )

    _run_detector(clean_db, monkeypatch)
    assert clean_db.execute(select(Alert)).scalars().all() == []


def test_another_ip_with_its_own_burst_raises_its_own_alert(
    clean_db, detector_source, monkeypatch
) -> None:
    """Each source IP is counted separately and can trigger its own alert."""
    from sentinel.common.clock import utcnow

    base = utcnow()
    for index in range(5):
        _persist_event(
            clean_db,
            detector_source,
            source_ip="198.51.100.7",
            event_type="login_failed",
            status_code=401,
            received_at=base + timedelta(seconds=index),
        )

    _run_detector(clean_db, monkeypatch)
    alerts = clean_db.execute(select(Alert)).scalars().all()
    assert len(alerts) == 1
    assert str(alerts[0].source_ip) == "198.51.100.7"


def test_the_worker_writes_a_heartbeat(clean_db, detector_source, monkeypatch) -> None:
    from sentinel.common.models import DetectorHeartbeat

    _run_detector(clean_db, monkeypatch)
    heartbeat = clean_db.get(DetectorHeartbeat, 1)
    assert heartbeat is not None
    assert heartbeat.last_seen_at is not None


def test_a_failing_job_stays_pending_and_is_retried(clean_db, detector_source, monkeypatch) -> None:
    from sentinel.common.clock import utcnow

    _persist_event(clean_db, detector_source, received_at=utcnow())

    import sentinel.detector.worker as worker_module

    class _Session:
        def __init__(self) -> None:
            self._session = clean_db

        def __getattr__(self, name):
            return getattr(self._session, name)

    monkeypatch.setattr(worker_module, "SessionLocal", lambda: _Session())

    detector = Detector()

    def _boom(*args, **kwargs):
        raise RuntimeError("transient database failure")

    monkeypatch.setattr(detector, "_evaluate_event", _boom)
    detector.run_once()

    job = clean_db.execute(select(DetectorJob)).scalar_one()
    assert job.status == "pending"
    assert job.attempts == 1
    # The failure message is sanitized: no payload and no credentials.
    assert job.last_error is not None
    assert "transient database failure" not in job.last_error
