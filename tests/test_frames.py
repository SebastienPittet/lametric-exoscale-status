"""Tests for lib.frames + lib.subscription + lib.cache (TDD)."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from lib.cache import CachedFetch, TtlCache
from lib.frames import MAX_FRAMES, FramesPayload, build_frames
from lib.models import (
    Lifecycle,
    Notice,
    NoticeType,
    PageStatus,
    Service,
    Status,
    StatusData,
    Zone,
    ZoneService,
)
from lib.subscription import Subscription, SubscriptionError, parse_subscription


def make_status_data(
    zones: tuple[Zone, ...] = (),
    services: tuple[Service, ...] = (),
    incidents: tuple[Notice, ...] = (),
    maintenances: tuple[Notice, ...] = (),
    page_status: PageStatus = PageStatus.DEGRADED,
) -> StatusData:
    return StatusData(
        page_status=page_status,
        services=services,
        zones=zones,
        incidents=incidents,
        maintenances=maintenances,
        fetched_at=datetime.now(UTC),
        errors=(),
    )


def zone(slug: str, name: str, *svcs: Service) -> Zone:
    return Zone(
        id=slug,
        slug=slug,
        name=name,
        services=tuple(
            ZoneService(slug=s.slug, name=s.name, status=s.status) for s in svcs
        ),
    )


def svc(slug: str, name: str, status: Status) -> Service:
    return Service(
        id=slug,
        slug=slug,
        name=name,
        status=status,
        scope="global" if not slug.startswith("c") else "containers",
        containers=(),
    )


def notice(
    title: str,
    lifecycle: str = "active",
    notice_type: str = "incident",
    starts_at: str | None = "2026-01-05T02:00:00Z",
    severity: str | None = None,
) -> Notice:
    return Notice(
        id=title,
        notice_type=NoticeType(notice_type),
        title=title,
        status="investigating",
        severity=severity,
        lifecycle=Lifecycle(lifecycle),
        starts_at=starts_at,
        ends_at=None,
        description="",
    )


ICONS: dict[str, str] = {
    "up": "120",
    "down-minor": "1067",
    "down-major": "124",
    "down-fire": "2715",
    "scheduled": "7419",
    "no-status": "625",
    "tool": "93",
}


def frame_texts(frames: FramesPayload) -> list[str]:
    return [frame["text"] for frame in frames["frames"]]


# ---------------- frames ----------------

def test_healthy_shows_single_frame() -> None:
    data = make_status_data(page_status=PageStatus.OPERATIONAL)
    frames = build_frames(data, "Exoscale", "17776", ICONS, Subscription())
    texts = frame_texts(frames)
    assert texts[0] == "Exoscale"
    assert texts[1] == "HEALTHY"
    assert len(texts) == 2


def test_incident_frames_use_zone_service_status() -> None:
    data = make_status_data(zones=(
        zone("ch-dk-2", "CH-DK-2", svc("compute", "Compute", Status.MAJOR)),
    ))
    frames = build_frames(data, "Exoscale", "17776", ICONS, Subscription())
    texts = frame_texts(frames)
    assert "CH-DK-2 Compute" in texts
    frame = next(f for f in frames["frames"] if f["text"] == "CH-DK-2 Compute")
    assert frame["icon"] == "124"


def test_critical_and_maintenance_icons() -> None:
    data = make_status_data(
        zones=(zone("de-fra-1", "DE-FRA-1",
                    svc("skl", "SKS", Status.CRITICAL),
                    svc("sos", "SOS", Status.MAINTENANCE)),),
        maintenances=(notice("SOS window", "pending", "maintenance"),),
    )
    frames = build_frames(data, "Exoscale", "17776", ICONS, Subscription())
    by_text = {f["text"]: f["icon"] for f in frames["frames"]}
    assert by_text["DE-FRA-1 SKS"] == "2715"
    assert by_text["DE-FRA-1 SOS"] == "7419"
    assert any("SOS window" in t for t in frame_texts(frames))


def test_unknown_status_icon() -> None:
    data = make_status_data(zones=(
        zone("x", "X", svc("a", "A", Status.UNKNOWN)),
    ))
    frames = build_frames(data, "Exoscale", "17776", ICONS, Subscription())
    frame = next(f for f in frames["frames"] if f["text"] == "X A")
    assert frame["icon"] == "625"


def test_frame_cap_with_overflow_notice() -> None:
    zones = tuple(
        zone(f"z{i:02d}", f"Z{i:02d}", svc(f"s{i}", f"S{i}", Status.MAJOR))
        for i in range(30)
    )
    data = make_status_data(zones=zones)
    frames = build_frames(data, "Exoscale", "17776", ICONS, Subscription())
    assert len(frames["frames"]) <= MAX_FRAMES
    assert "more" in frame_texts(frames)[-1]


def test_unavailable_data() -> None:
    data = StatusData(
        page_status=PageStatus.UNKNOWN,
        services=(),
        zones=(),
        incidents=(),
        maintenances=(),
        fetched_at=None,
        errors=(),
    )
    frames = build_frames(data, "Exoscale", "17776", ICONS, Subscription())
    assert frame_texts(frames)[-1] == "Status unavailable"


def test_subscription_zones_filter() -> None:
    data = make_status_data(zones=(
        zone("ch-gva-2", "CH-GVA-2", svc("api", "API", Status.MINOR)),
        zone("ch-dk-2", "CH-DK-2", svc("compute", "Compute", Status.MAJOR)),
    ))
    sub = Subscription(zones=frozenset({"ch-gva-2"}), services=frozenset())
    frames = build_frames(data, "Exoscale", "17776", ICONS, sub)
    assert "CH-GVA-2 API" in frame_texts(frames)
    assert not any("CH-DK-2" in t for t in frame_texts(frames))


def test_subscription_services_filter() -> None:
    data = make_status_data(zones=(
        zone("ch-dk-2", "CH-DK-2",
             svc("compute", "Compute", Status.MAJOR),
             svc("api", "API", Status.MINOR)),
    ))
    sub = Subscription(zones=frozenset(), services=frozenset({"compute"}))
    frames = build_frames(data, "Exoscale", "17776", ICONS, sub)
    assert "CH-DK-2 Compute" in frame_texts(frames)
    assert not any("API" in t for t in frame_texts(frames))


def test_subscription_no_match() -> None:
    data = make_status_data(zones=(
        zone("ch-dk-2", "CH-DK-2", svc("compute", "Compute", Status.MAJOR)),
    ))
    sub = Subscription(zones=frozenset({"nope"}), services=frozenset())
    frames = build_frames(data, "Exoscale", "17776", ICONS, sub)
    assert frame_texts(frames)[-1] == "No subscribed services matched"


# ---------------- subscription ----------------

def test_parse_subscription_comma_and_case() -> None:
    sub = parse_subscription({"zones": "CH-GVA-2,ch-dk-2", "services": "Compute,API"})
    assert sub.zones == frozenset({"ch-gva-2", "ch-dk-2"})
    assert sub.services == frozenset({"compute", "api"})


def test_parse_subscription_list_values() -> None:
    sub = parse_subscription({"zones": ["A", "B"]})
    assert sub.zones == frozenset({"a", "b"})


def test_parse_subscription_empty() -> None:
    sub = parse_subscription({})
    assert sub.zones == frozenset() and sub.services == frozenset()
    assert sub.empty


def test_parse_subscription_invalid_chars() -> None:
    with pytest.raises(SubscriptionError):
        parse_subscription({"zones": "bad;rm"})


def test_parse_subscription_too_many_tokens() -> None:
    with pytest.raises(SubscriptionError):
        parse_subscription({"zones": ",".join(f"z{i}" for i in range(21))})


# ---------------- cache ----------------

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
