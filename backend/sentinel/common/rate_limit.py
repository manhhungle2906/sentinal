"""In-memory sliding-window rate limiter.

The MVP runs a single Core and a single Ingest process, so an in-process
limiter is sufficient and needs no extra datastore. Limits are configurable
through environment settings and documented in docs/architecture.md.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window = timedelta(seconds=window_seconds)
        self._hits: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, now: datetime) -> tuple[bool, int]:
        """Return (allowed, remaining) for ``key`` at ``now``.

        The window is half-open: (now - window, now].
        """
        with self._lock:
            hits = self._hits[key]
            cutoff = now - self.window
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                return False, 0
            hits.append(now)
            return True, self.limit - len(hits)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
