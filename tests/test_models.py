"""Tests for lib.models (TDD)."""
from lib.models import Status, Zone, ZoneService, worst


def test_worst_ranking():
    assert worst([Status.OK, Status.MINOR]) == Status.MINOR
    assert worst([Status.MAJOR, Status.CRITICAL]) == Status.CRITICAL
    assert worst([Status.MAINTENANCE, Status.MINOR]) == Status.MINOR
    assert worst([Status.OK]) == Status.OK


def test_worst_empty_is_ok():
    assert worst([]) == Status.OK


def test_zone_worst_status():
    zone = Zone(id="c1", slug="ch-dk-2", name="CH-DK-2", services=(
        ZoneService(slug="api", name="API", status=Status.OK),
        ZoneService(slug="compute", name="Compute", status=Status.MAJOR),
    ))
    assert zone.worst_status == Status.MAJOR


def test_zone_without_services_is_ok():
    zone = Zone(id="c2", slug="x", name="X", services=())
    assert zone.worst_status == Status.OK
