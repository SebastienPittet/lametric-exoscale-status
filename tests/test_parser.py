"""Tests for lib.statuspal_parser (TDD)."""
from lib.models import Status
from lib.statuspal_parser import (
    parse_notices,
    parse_status_page,
    parse_services,
    parse_zones,
    status_from_value,
    to_plain_text,
)


def test_parse_status_page(status_page_payload):
    assert parse_status_page(status_page_payload) == "degraded"


def test_parse_status_page_missing_data():
    assert parse_status_page({}) == "unknown"
    assert parse_status_page({"data": {}}) == "unknown"


def test_parse_services(services_payload):
    services = parse_services(services_payload)
    assert len(services) == 7
    compute = next(s for s in services if s.slug == "compute")
    assert compute.name == "Compute"
    assert compute.status == Status.MAJOR
    assert compute.containers == ("ch-dk-2",)
    assert compute.scope == "containers"


def test_parse_services_skips_malformed():
    payload = {"data": [
        "not-a-dict",
        {"id": "1", "status": "ok"},  # missing name -> skipped
        {"id": "2", "name": "OK One", "status": "weird-value"},
    ]}
    services = parse_services(payload)
    assert len(services) == 1
    assert services[0].name == "OK One"
    assert services[0].status == Status.UNKNOWN


def test_parse_services_unknown_status():
    assert status_from_value("ok") == Status.OK
    assert status_from_value("CRITICAL") == Status.CRITICAL
    assert status_from_value("maintenance") == Status.MAINTENANCE
    assert status_from_value(None) == Status.OK
    assert status_from_value("bogus") == Status.UNKNOWN


def test_parse_zones(containers_payload):
    zones = parse_zones(containers_payload)
    assert len(zones) == 3
    dk2 = next(z for z in zones if z.slug == "ch-dk-2")
    assert dk2.name == "CH-DK-2"
    assert dk2.worst_status == Status.MAJOR


def test_parse_zones_skips_malformed():
    assert parse_zones({"data": [None, {"name": "NoSlug"}]}) == ()


def test_parse_notices(notices_payload):
    incidents, maintenances = parse_notices(notices_payload)
    # only non-completed incidents
    assert [i.title for i in incidents] == ["Compute outage in CH-DK-2"]
    # pending + active maintenances
    assert {m.title for m in maintenances} == {
        "SOS maintenance window", "SKS patching in progress"}
    assert incidents[0].description == "We are investigating a Compute outage."
    assert incidents[0].severity == "major"
    assert incidents[0].starts_at == "2026-01-02T10:00:00Z"


def test_parse_notices_missing_data():
    assert parse_notices({}) == ([], [])


def test_to_plain_text():
    assert to_plain_text("<p>hello <b>world</b></p>") == "hello world"
    assert to_plain_text("a  b\n\tc") == "a b c"
    assert to_plain_text(None) == ""
