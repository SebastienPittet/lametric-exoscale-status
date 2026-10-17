"""Tests for lib.models (TDD)."""
from lib.models import Status, Zone, ZoneService, worst


def test_worst_ranking() -> None:
    assert worst([Status.OK, Status.MINOR]) == Status.MINOR
    assert worst([Status.MAJOR, Status.CRITICAL]) == Status.CRITICAL
    assert worst([Status.MAINTENANCE, Status.MINOR]) == Status.MINOR
    assert worst([Status.OK]) == Status.OK


def test_worst_empty_is_ok() -> None:
    assert worst([]) == Status.OK


def test_zone_worst_status() -> None:
    zone = Zone(id="c1", slug="ch-dk-2", name="CH-DK-2", services=(
        ZoneService(slug="api", name="API", status=Status.OK),
        ZoneService(slug="compute", name="Compute", status=Status.MAJOR),
    ))
    assert zone.worst_status == Status.MAJOR


def test_zone_without_services_is_ok() -> None:
    zone = Zone(id="c2", slug="x", name="X", services=())
    assert zone.worst_status == Status.OK
