"""Security helpers: response headers and a sliding-window rate limiter."""
from __future__ import annotations

import threading
import time

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}

_MAX_TRACKED_KEYS = 10000


class RateLimiter:
    """A thread-safe sliding-window rate limiter, keyed by client.

    Deliberately self-contained (no flask-limiter dependency): the app
    needs exactly one global per-client limit and zero extra
    dependencies. Note: with multiple gunicorn workers the limit applies
    per worker; raise rate_limit_per_minute accordingly or move the
    limit to the edge (reverse proxy) if a strict global cap matters.

    Memory is bounded: when more than _MAX_TRACKED_KEYS clients are tracked,
    the oldest one is dropped.
    """

    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        self._max_requests = max_requests
        self._window = float(window_seconds)
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Record a hit for key; return True when it is within the limit."""
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            if len(self._hits) > _MAX_TRACKED_KEYS:
                oldest = min(
                    self._hits, key=lambda k: min(self._hits[k], default=now)
                )
                del self._hits[oldest]
            stamps = [t for t in self._hits.get(key, []) if t > cutoff]
            if len(stamps) < self._max_requests:
                stamps.append(now)
                self._hits[key] = stamps
                return True
            if stamps:
                self._hits[key] = stamps
            else:
                self._hits.pop(key, None)
            return False
