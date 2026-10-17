"""Tests for lib.cache (TDD)."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from lib.cache import CachedFetch, TtlCache


def test_cache_set_get_and_expiry() -> None:
    cache = TtlCache[int](ttl_seconds=0.05)
    assert cache.get("k") is None
    cache.set("k", 42)
    assert cache.get("k") == 42
    time.sleep(0.06)
    assert cache.get("k") is None
    cache.set("k", 1)
    cache.invalidate("k")
    assert cache.get("k") is None


def test_cache_single_flight() -> None:
    cache = TtlCache[int](ttl_seconds=60)
    calls: list[int] = []

    def fetcher() -> int:
        calls.append(1)
        time.sleep(0.05)
        return len(calls)

    fetch = CachedFetch(fetcher, cache, key="k")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: fetch.get(), range(16)))
    assert len(calls) == 1
    assert all(r == results[0] for r in results)
