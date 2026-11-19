"""Unit tests for the detection rule engine.

These tests use a controlled clock and synthetic events; they never depend on
wall time or on a database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sentinel.detector.rules import (
    RuleDefinition,
    default_rules,
    evaluate_rule,
    in_detection_window,
    qualifies_for_rule,
    select_window_events,
)

SOURCE_ID = uuid.uuid4()
OTHER_SOURCE_ID = uuid.uuid4()


class FakeEvent:
    """Minimal event satisfying the QualifyingEvent protocol."""

    def __init__(
        self,
        *,
        source_id: uuid.UUID = SOURCE_ID,
        source_ip: str = "203.0.113.10",
        received_at: datetime,
        ingest_seq: int,
        event_type: str = "request",
        status_code: int = 200,
    ) -> None:
        self.id = uuid.uuid4()
        self.source_id = source_id
        self.source_ip = source_ip
        self.received_at = received_at
        self.ingest_seq = ingest_seq
        self.event_type = event_type
        self.status_code = status_code
        self.route_template = "/api/products"
        self.method = "GET"


def rules() -> list[RuleDefinition]:
    return default_rules(
        failed_login_threshold=5,
        failed_login_window_seconds=120,
        failed_login_severity="high",
        request_volume_threshold=101,
        request_volume_window_seconds=60,
        request_volume_severity="medium",
        access_denial_threshold=10,
        access_denial_window_seconds=300,
        access_denial_severity="medium",
    )


def rule_by_key(key: str) -> RuleDefinition:
    return next(rule for rule in rules() if rule.key == key)


def test_detection_window_excludes_start_and_includes_end() -> None:
    as_of = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    window = timedelta(minutes=2)

    assert not in_detection_window(as_of - window, as_of, window)
    assert in_detection_window(as_of, as_of, window)


def test_default_rule_thresholds_match_the_specification() -> None:
    by_key = {rule.key: rule for rule in rules()}
    assert by_key["failed_login_burst"].threshold == 5
    assert by_key["failed_login_burst"].window == timedelta(minutes=2)
    assert by_key["failed_login_burst"].severity == "high"
    assert by_key["high_request_volume"].threshold == 101
    assert by_key["high_request_volume"].window == timedelta(minutes=1)
    assert by_key["high_request_volume"].severity == "medium"
    assert by_key["repeated_access_denial"].threshold == 10
    assert by_key["repeated_access_denial"].window == timedelta(minutes=5)
    assert by_key["repeated_access_denial"].severity == "medium"


# ---------------------------------------------------------------------------
# Qualifying events
# ---------------------------------------------------------------------------
def test_failed_login_burst_counts_only_login_failed_events() -> None:
    rule = rule_by_key("failed_login_burst")
    login_failed = FakeEvent(
        received_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        ingest_seq=1,
        event_type="login_failed",
        status_code=401,
    )
    plain = FakeEvent(
        received_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        ingest_seq=2,
        event_type="request",
        status_code=401,
    )
    assert qualifies_for_rule(login_failed, rule)
    assert not qualifies_for_rule(plain, rule)


def test_high_request_volume_counts_every_validated_request() -> None:
    rule = rule_by_key("high_request_volume")
    login_failed = FakeEvent(
        received_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        ingest_seq=1,
        event_type="login_failed",
        status_code=401,
    )
    assert qualifies_for_rule(login_failed, rule)


def test_repeated_access_denial_excludes_the_failed_login_stream() -> None:
    rule = rule_by_key("repeated_access_denial")
    denial = FakeEvent(
        received_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        ingest_seq=1,
        status_code=403,
    )
    login_failed = FakeEvent(
        received_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        ingest_seq=2,
        event_type="login_failed",
        status_code=401,
    )
    assert qualifies_for_rule(denial, rule)
    assert not qualifies_for_rule(login_failed, rule)


# ---------------------------------------------------------------------------
# Threshold behaviour
# ---------------------------------------------------------------------------
def _events(count: int, *, start: datetime, interval_ms: int = 1000, **kwargs):
    return [
        FakeEvent(
            received_at=start + timedelta(milliseconds=interval_ms * index),
            ingest_seq=index + 1,
            **kwargs,
        )
        for index in range(count)
    ]


@pytest.mark.parametrize("rule_key", ["failed_login_burst", "repeated_access_denial"])
def test_one_below_threshold_does_not_trigger(rule_key: str) -> None:
    rule = rule_by_key(rule_key)
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    kwargs = (
        {"event_type": "login_failed", "status_code": 401}
        if rule_key == "failed_login_burst"
        else {"status_code": 403}
    )
    events = _events(rule.threshold - 1, start=start, **kwargs)
    decision = evaluate_rule(rule, events, events[-1])
    assert decision.count_after == rule.threshold - 1
    assert decision.triggered is False


@pytest.mark.parametrize("rule_key", ["failed_login_burst", "repeated_access_denial"])
def test_exact_threshold_triggers(rule_key: str) -> None:
    rule = rule_by_key(rule_key)
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    kwargs = (
        {"event_type": "login_failed", "status_code": 401}
        if rule_key == "failed_login_burst"
        else {"status_code": 403}
    )
    events = _events(rule.threshold, start=start, **kwargs)
    decision = evaluate_rule(rule, events, events[-1])
    assert decision.count_after == rule.threshold
    assert decision.count_before == rule.threshold - 1
    assert decision.triggered is True


def test_high_request_volume_one_below_and_exact_threshold() -> None:
    rule = rule_by_key("high_request_volume")
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    # 101 events must fit inside the 60 second window, so they are spaced
    # 500 ms apart.
    below = _events(rule.threshold - 1, start=start, interval_ms=500)
    assert evaluate_rule(rule, below, below[-1]).triggered is False

    exact = _events(rule.threshold, start=start, interval_ms=500)
    decision = evaluate_rule(rule, exact, exact[-1])
    assert decision.count_after == rule.threshold
    assert decision.triggered is True


def test_no_new_alert_while_the_count_stays_above_the_threshold() -> None:
    rule = rule_by_key("failed_login_burst")
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    events = _events(rule.threshold + 2, start=start, event_type="login_failed", status_code=401)
    # The trigger at index threshold-1 crosses; the next event does not.
    crossing = evaluate_rule(rule, events, events[rule.threshold - 1])
    later = evaluate_rule(rule, events, events[rule.threshold])
    assert crossing.triggered is True
    assert later.triggered is False


# ---------------------------------------------------------------------------
# Window boundary
# ---------------------------------------------------------------------------
def test_event_outside_the_window_is_not_counted() -> None:
    rule = rule_by_key("failed_login_burst")
    as_of = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    old = FakeEvent(
        received_at=as_of - timedelta(seconds=121),
        ingest_seq=1,
        event_type="login_failed",
        status_code=401,
    )
    trigger = FakeEvent(
        received_at=as_of,
        ingest_seq=2,
        event_type="login_failed",
        status_code=401,
    )
    decision = evaluate_rule(rule, [old, trigger], trigger)
    assert decision.count_after == 1
    assert decision.triggered is False


def test_event_exactly_on_the_window_start_is_excluded() -> None:
    rule = rule_by_key("failed_login_burst")
    as_of = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    boundary = FakeEvent(
        received_at=as_of - rule.window,
        ingest_seq=1,
        event_type="login_failed",
        status_code=401,
    )
    trigger = FakeEvent(
        received_at=as_of,
        ingest_seq=2,
        event_type="login_failed",
        status_code=401,
    )
    decision = evaluate_rule(rule, [boundary, trigger], trigger)
    assert decision.count_after == 1


# ---------------------------------------------------------------------------
# Source / IP separation
# ---------------------------------------------------------------------------
def test_events_from_another_source_are_not_counted() -> None:
    rule = rule_by_key("failed_login_burst")
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    others = _events(
        rule.threshold,
        start=start,
        event_type="login_failed",
        status_code=401,
        source_id=OTHER_SOURCE_ID,
    )
    trigger = FakeEvent(
        received_at=start + timedelta(seconds=10),
        ingest_seq=100,
        event_type="login_failed",
        status_code=401,
    )
    decision = evaluate_rule(rule, [*others, trigger], trigger)
    assert decision.count_after == 1
    assert decision.triggered is False


def test_events_from_another_ip_are_not_counted() -> None:
    rule = rule_by_key("failed_login_burst")
    start = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    others = _events(
        rule.threshold,
        start=start,
        event_type="login_failed",
        status_code=401,
        source_ip="198.51.100.7",
    )
    trigger = FakeEvent(
        received_at=start + timedelta(seconds=10),
        ingest_seq=100,
        event_type="login_failed",
        status_code=401,
    )
    decision = evaluate_rule(rule, [*others, trigger], trigger)
    assert decision.count_after == 1
    assert decision.triggered is False


# ---------------------------------------------------------------------------
# Stable ordering
# ---------------------------------------------------------------------------
def test_events_with_the_same_timestamp_are_ordered_by_ingest_sequence() -> None:
    rule = rule_by_key("failed_login_burst")
    as_of = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    events = [
        FakeEvent(
            received_at=as_of,
            ingest_seq=index,
            event_type="login_failed",
            status_code=401,
        )
        for index in range(1, 6)
    ]
    trigger = events[2]
    selected = select_window_events(events, rule, as_of, trigger)
    # Only the events up to the trigger's sequence at that timestamp count.
    assert [event.ingest_seq for event in selected] == [1, 2, 3]
    decision = evaluate_rule(rule, events, trigger)
    assert decision.count_after == 3
