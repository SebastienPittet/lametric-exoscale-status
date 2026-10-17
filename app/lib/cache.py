"""Thread-safe TTL cache and single-flight fetch helper."""
from __future__ import annotations

import threading
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class TtlCache:
    """A simple in-memory cache with a per-entry TTL (monotonic clock)."""

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = float(ttl_seconds)
        self._store: dict[str, tuple[object, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        """Return the cached value, or None when absent or expired (purged)."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() >= expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: object) -> None:
        """Store a value with the configured TTL."""
        with self._lock:
            self._store[key] = (value, time.monotonic() + self._ttl)

    def invalidate(self, key: str) -> None:
        """Remove a key from the cache."""
        with self._lock:
            self._store.pop(key, None)


class CachedFetch:
    """Fetch a value through a cache, with a single in-flight fetch per key.

    Concurrent callers share one fetcher call (lock + double-check).
    """

    def __init__(
        self,
        fetcher: Callable[[], T],
        cache: TtlCache,
        key: str = "default",
    ) -> None:
        self._fetcher = fetcher
        self._cache = cache
        self._key = key
        self._lock = threading.Lock()

    def get(self) -> T:
        value = self._cache.get(self._key)
        if value is not None:
            return value
        with self._lock:
            value = self._cache.get(self._key)
            if value is not None:
                return value
            value = self._fetcher()
            self._cache.set(self._key, value)
            return value
