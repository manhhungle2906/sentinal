"""Injectable clock so rule logic and tests never depend on wall time."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def system_clock() -> datetime:
    return utcnow()


def fixed_clock(moment: datetime) -> Clock:
    """Return a clock frozen at ``moment`` (tests)."""
    if moment.tzinfo is None:
        raise ValueError("fixed_clock requires a timezone-aware datetime")
    return lambda: moment


def ensure_utc(value: datetime) -> datetime:
    """Normalize any datetime to UTC, assuming naive values are UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
