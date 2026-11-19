"""Synthetic detection scenario generator.

The generator produces **event records**, not suspicious HTTP traffic. Every
record is submitted to the local ingestion endpoint of the configured
environment. Event ids are deterministic so a seeding run can be repeated
without creating duplicates.

Scenarios are isolated by source id and source IP so the expected alert for
each scenario is unambiguous:

- ``failed_login_burst``  : 5 explicit login_failed events, one IP
- ``high_request_volume`` : 101 request events, another IP
- ``repeated_access_denial``: 10 HTTP 403 events, a third IP
- ``under_threshold``     : one event below each threshold, separate IPs
- ``normal``              : ordinary traffic and an occasional access denial
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# Reserved documentation IP ranges (RFC 5737) are used for demo telemetry.
IP_FAILED_LOGIN = "203.0.113.11"
IP_HIGH_VOLUME = "203.0.113.12"
IP_ACCESS_DENIAL = "203.0.113.13"
IP_UNDER_LOGIN = "203.0.113.14"
IP_UNDER_DENIAL = "203.0.113.16"
IP_UNDER_VOLUME = "203.0.113.17"
IP_NORMAL = "203.0.113.15"

# A fixed namespace keeps the generated event ids deterministic. Bump the
# namespace only when the generated payload changes, so a seeding run stays an
# identical retry against the events of a previous run.
EVENT_NAMESPACE = uuid.UUID("6f2b1c34-6f5a-4a1e-9d2f-2c0b7a4e5f11")

# A fixed base moment keeps the generated payloads byte-identical between
# runs. The detection rules decide on the server receipt timestamp, so the
# client timestamp only has to be stable, not recent. A stable payload makes a
# repeated seeding run an identical retry (200) instead of a conflicting
# duplicate (409).
DEMO_BASE_TIME = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


def deterministic_event_id(scenario: str, index: int) -> uuid.UUID:
    """Return a stable event id for a scenario and index."""
    return uuid.uuid5(EVENT_NAMESPACE, f"{scenario}:{index}")


@dataclass(frozen=True)
class SyntheticEvent:
    event_id: uuid.UUID
    event_type: str
    source_ip: str
    route_template: str
    method: str
    status_code: int
    duration_ms: int
    occurred_at: datetime

    def to_payload(self) -> dict:
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "source_ip": self.source_ip,
            "route_template": self.route_template,
            "method": self.method,
            "status_code": self.status_code,
            "duration_ms": self.duration_ms,
        }


def _event(
    scenario: str,
    index: int,
    *,
    source_ip: str,
    event_type: str = "request",
    route_template: str = "GET /api/products",
    method: str = "GET",
    status_code: int = 200,
    duration_ms: int = 25,
    occurred_at: datetime,
) -> SyntheticEvent:
    return SyntheticEvent(
        event_id=deterministic_event_id(scenario, index),
        event_type=event_type,
        source_ip=source_ip,
        route_template=route_template,
        method=method,
        status_code=status_code,
        duration_ms=duration_ms,
        occurred_at=occurred_at,
    )


def failed_login_burst_scenario(base: datetime) -> list[SyntheticEvent]:
    """5 explicit login failures, exactly at the threshold."""
    events = []
    for index in range(5):
        events.append(
            _event(
                "failed_login_burst",
                index,
                source_ip=IP_FAILED_LOGIN,
                event_type="login_failed",
                route_template="POST /auth/login",
                method="POST",
                status_code=401,
                occurred_at=base + timedelta(seconds=index * 5),
            )
        )
    return events


def high_request_volume_scenario(base: datetime) -> list[SyntheticEvent]:
    """101 request events, exactly at the threshold, inside one minute."""
    events = []
    for index in range(101):
        events.append(
            _event(
                "high_request_volume",
                index,
                source_ip=IP_HIGH_VOLUME,
                occurred_at=base + timedelta(milliseconds=index * 500),
            )
        )
    return events


def repeated_access_denial_scenario(base: datetime) -> list[SyntheticEvent]:
    """10 HTTP 403 responses, exactly at the threshold."""
    events = []
    for index in range(10):
        events.append(
            _event(
                "repeated_access_denial",
                index,
                source_ip=IP_ACCESS_DENIAL,
                status_code=403,
                occurred_at=base + timedelta(seconds=index * 10),
            )
        )
    return events


def under_threshold_scenario(base: datetime) -> list[SyntheticEvent]:
    """One event below each threshold, on separate IPs.

    The three controls use different source IPs because the request-volume rule
    counts every request event, including denials and login failures. Sharing
    an IP would let one control push another rule over its threshold.
    """
    events = []
    for index in range(4):
        events.append(
            _event(
                "under_threshold_failed_login",
                index,
                source_ip=IP_UNDER_LOGIN,
                event_type="login_failed",
                route_template="POST /auth/login",
                method="POST",
                status_code=401,
                occurred_at=base + timedelta(seconds=index * 5),
            )
        )
    for index in range(9):
        events.append(
            _event(
                "under_threshold_access_denial",
                index,
                source_ip=IP_UNDER_DENIAL,
                status_code=403,
                occurred_at=base + timedelta(seconds=index * 10),
            )
        )
    for index in range(100):
        events.append(
            _event(
                "under_threshold_request_volume",
                index,
                source_ip=IP_UNDER_VOLUME,
                occurred_at=base + timedelta(milliseconds=index * 500),
            )
        )
    return events


def normal_activity_scenario(base: datetime) -> list[SyntheticEvent]:
    """Ordinary traffic plus one occasional access denial."""
    events = []
    for index in range(12):
        events.append(
            _event(
                "normal",
                index,
                source_ip=IP_NORMAL,
                occurred_at=base + timedelta(seconds=index * 20),
            )
        )
    events.append(
        _event(
            "normal_denial",
            0,
            source_ip=IP_NORMAL,
            status_code=403,
            occurred_at=base + timedelta(seconds=250),
        )
    )
    return events


SCENARIOS: dict[str, callable] = {
    "failed_login_burst": failed_login_burst_scenario,
    "high_request_volume": high_request_volume_scenario,
    "repeated_access_denial": repeated_access_denial_scenario,
    "under_threshold": under_threshold_scenario,
    "normal": normal_activity_scenario,
}


def build_scenario(name: str, base: datetime | None = None) -> list[SyntheticEvent]:
    """Build the events for one scenario."""
    moment = base or DEMO_BASE_TIME
    builder = SCENARIOS[name]
    return builder(moment)


def build_all(base: datetime | None = None) -> list[SyntheticEvent]:
    """Build every scenario, isolated from each other."""
    moment = base or DEMO_BASE_TIME
    events: list[SyntheticEvent] = []
    for name in SCENARIOS:
        events.extend(build_scenario(name, moment))
    return events
