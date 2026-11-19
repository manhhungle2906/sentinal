"""Detection rules.

The rule engine is pure: it receives already-persisted events and returns the
rule decisions. Every time-dependent decision uses the server receipt time and
an injected clock, so tests never depend on wall time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from sentinel.common.constants import EventType


class QualifyingEvent(Protocol):
    """Minimal shape the rule engine needs from a persisted event."""

    id: object
    source_id: object
    source_ip: str
    received_at: datetime
    ingest_seq: int
    route_template: str
    method: str
    status_code: int
    event_type: str


def in_detection_window(received_at: datetime, as_of: datetime, window: timedelta) -> bool:
    """Return True when ``received_at`` falls inside the half-open window.

    The counting interval is ``(as_of - window, as_of]``: the start boundary is
    excluded and the end boundary is included.
    """
    return as_of - window < received_at <= as_of


@dataclass(frozen=True)
class RuleDefinition:
    key: str
    description: str
    threshold: int
    window: timedelta
    severity: str

    @property
    def window_seconds(self) -> int:
        return int(self.window.total_seconds())


def qualifies_for_rule(event: QualifyingEvent, rule: RuleDefinition) -> bool:
    """Return True when the event is counted by the rule."""
    if rule.key == "failed_login_burst":
        return event.event_type == EventType.LOGIN_FAILED.value
    if rule.key == "high_request_volume":
        # Every validated request event counts, login events included.
        return True
    if rule.key == "repeated_access_denial":
        # HTTP 401/403 outside the explicit failed-login stream.
        return event.status_code in (401, 403) and event.event_type != EventType.LOGIN_FAILED.value
    raise ValueError(f"unknown rule key: {rule.key}")


def select_window_events(
    events: list[QualifyingEvent],
    rule: RuleDefinition,
    as_of: datetime,
    trigger: QualifyingEvent,
) -> list[QualifyingEvent]:
    """Return the events counted in the rule window ending at the trigger.

    Only events received in ``(as_of - window, as_of]`` are counted. Counting
    is separated per source id and per source IP: events from another source
    or another IP never contribute to the count.

    When several events share the receipt timestamp ``as_of``, only those with
    an ingestion sequence up to the trigger's sequence are counted, so the
    worker and the event query use the same stable order.
    """
    selected: list[QualifyingEvent] = []
    for event in events:
        if event.source_id != trigger.source_id:
            continue
        if event.source_ip != trigger.source_ip:
            continue
        if not in_detection_window(event.received_at, as_of, rule.window):
            continue
        if event.received_at == as_of and event.ingest_seq > trigger.ingest_seq:
            continue
        if not qualifies_for_rule(event, rule):
            continue
        selected.append(event)
    return selected


@dataclass(frozen=True)
class RuleDecision:
    """Outcome of evaluating one rule against one trigger event."""

    rule: RuleDefinition
    triggered: bool
    count_after: int
    count_before: int
    interval_start: datetime
    interval_end: datetime
    evidence_ids: list[object]


def evaluate_rule(
    rule: RuleDefinition,
    events: list[QualifyingEvent],
    trigger: QualifyingEvent,
) -> RuleDecision:
    """Evaluate one rule for one trigger event.

    A crossing is detected by comparing the window count before and after the
    current qualifying event is included. An alert is raised only when the
    count moves from below the threshold to at-or-above the threshold.
    """
    window_events = select_window_events(events, rule, trigger.received_at, trigger)
    count_after = len(window_events)
    count_before = count_after - 1 if qualifies_for_rule(trigger, rule) else count_after

    triggered = count_before < rule.threshold <= count_after
    interval_start = trigger.received_at - rule.window
    return RuleDecision(
        rule=rule,
        triggered=triggered,
        count_after=count_after,
        count_before=count_before,
        interval_start=interval_start,
        interval_end=trigger.received_at,
        evidence_ids=[event.id for event in window_events],
    )


def default_rules(
    failed_login_threshold: int,
    failed_login_window_seconds: int,
    failed_login_severity: str,
    request_volume_threshold: int,
    request_volume_window_seconds: int,
    request_volume_severity: str,
    access_denial_threshold: int,
    access_denial_window_seconds: int,
    access_denial_severity: str,
) -> list[RuleDefinition]:
    """Build the rule set from the configured defaults."""
    return [
        RuleDefinition(
            key="failed_login_burst",
            description=(
                "Explicit login_failed events from the same source and source IP "
                f"reaching {failed_login_threshold} within "
                f"{failed_login_window_seconds} seconds"
            ),
            threshold=failed_login_threshold,
            window=timedelta(seconds=failed_login_window_seconds),
            severity=failed_login_severity,
        ),
        RuleDefinition(
            key="high_request_volume",
            description=(
                "All validated request events from the same source and source IP "
                f"reaching {request_volume_threshold} within "
                f"{request_volume_window_seconds} seconds"
            ),
            threshold=request_volume_threshold,
            window=timedelta(seconds=request_volume_window_seconds),
            severity=request_volume_severity,
        ),
        RuleDefinition(
            key="repeated_access_denial",
            description=(
                "HTTP 401/403 responses outside the failed-login stream from the "
                f"same source and source IP reaching {access_denial_threshold} "
                f"within {access_denial_window_seconds} seconds"
            ),
            threshold=access_denial_threshold,
            window=timedelta(seconds=access_denial_window_seconds),
            severity=access_denial_severity,
        ),
    ]
