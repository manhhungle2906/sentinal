"""Detector health probe.

The detector is a background worker without an HTTP server, so the container
healthcheck asks this module directly. It exits 0 when the heartbeat recorded
in PostgreSQL is fresh, and 1 otherwise. No internal details are printed.
"""

from __future__ import annotations

import sys

from sqlalchemy import text

from sentinel.common.clock import utcnow
from sentinel.common.db import SessionLocal
from sentinel.common.models import DetectorHeartbeat

MAX_HEARTBEAT_AGE_SECONDS = 60


def heartbeat_age_seconds() -> float | None:
    """Return the age of the detector heartbeat in seconds, or None."""
    session = SessionLocal()
    try:
        row = session.get(DetectorHeartbeat, 1)
        if row is None:
            return None
        last_seen = row.last_seen_at
        if last_seen.tzinfo is None:
            from datetime import UTC

            last_seen = last_seen.replace(tzinfo=UTC)
        return (utcnow() - last_seen).total_seconds()
    finally:
        session.close()


def main() -> int:
    try:
        age = heartbeat_age_seconds()
    except Exception:
        print("detector heartbeat unavailable", file=sys.stderr)
        return 1
    if age is None:
        print("detector has never reported a heartbeat", file=sys.stderr)
        return 1
    if age > MAX_HEARTBEAT_AGE_SECONDS:
        print("detector heartbeat is stale", file=sys.stderr)
        return 1
    # The probe only reports liveness; no internal state is exposed.
    with SessionLocal() as session:
        session.execute(text("SELECT 1"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
