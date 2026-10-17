"""Tests for lib.statuspal_parser (TDD) - public StatusPal API v2 shape."""
from __future__ import annotations

from lib.models import Notice, Status
from lib.statuspal_parser import (
    page_status_from_value,
    parse_notices,
    parse_status_page,
    parse_services,
    parse_zones,
    status_from_value,
    to_plain_text,
)


def test_parse_status_page(summary_payload: dict[str, object]) -> None:
    assert parse_status_page(summary_payload) == "degraded"


def test_parse_status_page_mappings() -> None:
    def payload(value: object) -> dict[str, object]:
        return {"status_page": {"name": "Exoscale", "current_incident_type": value}}

    assert parse_status_page(payload(None)) == "operational"
    assert parse_status_page(payload("none")) == "operational"
    assert parse_status_page(payload("ok")) == "operational"
    assert parse_status_page(payload("minor")) == "degraded"
    assert parse_status_page(payload("major")) == "unavailable"
    assert parse_status_page(payload("critical")) == "unavailable"
    assert parse_status_page(payload("bogus")) == "unknown"
    assert parse_status_page({}) == "unknown"


def test_page_status_from_value() -> None:
    assert page_status_from_value(None) == "operational"
    assert page_status_from_value("") == "operational"
    assert page_status_from_value("none") == "operational"
    assert page_status_from_value("minor") == "degraded"
    assert page_status_from_value("critical") == "unavailable"
    assert page_status_from_value("maintenance") == "unknown"


def test_parse_services(summary_payload: dict[str, object]) -> None:
    services = parse_services(summary_payload)
    # only children-less (global) services, zones excluded
    assert len(services) == 4
    portal = next(s for s in services if s.name == "Portal")
    assert portal.scope == "global"
    assert portal.slug == "portal"
    assert portal.status == Status.OK
    assert portal.containers == ()
    billing = next(s for s in services if s.name == "Billing")
    assert billing.status == Status.MINOR


def test_parse_services_skips_malformed() -> None:
    payload: dict[str, object] = {"services": [
        "not-a-dict",
        {"id": 1, "current_incident_type": "ok"},  # missing name -> skipped
        {"id": 2, "name": "A Zone", "children": [{"name": "Child"}]},  # zone, not global
        {"id": 3, "name": "OK One", "children": [], "current_incident_type": "weird-value"},
    ]}
    services = parse_services(payload)
    assert len(services) == 1
    assert services[0].name == "OK One"
    assert services[0].status == Status.UNKNOWN


def test_status_from_value() -> None:
    assert status_from_value("ok") == Status.OK
    assert status_from_value("none") == Status.OK
    assert status_from_value("CRITICAL") == Status.CRITICAL
    assert status_from_value("maintenance") == Status.MAINTENANCE
    assert status_from_value("scheduled") == Status.MAINTENANCE
    assert status_from_value(None) == Status.OK
    assert status_from_value("bogus") == Status.UNKNOWN


def test_parse_zones(summary_payload: dict[str, object]) -> None:
    zones = parse_zones(summary_payload)
    assert len(zones) == 3
    dk2 = next(z for z in zones if z.slug == "ch-dk-2")
    assert dk2.name == "CH-DK-2"
    assert dk2.worst_status == Status.MAJOR
    assert [s.name for s in dk2.services] == ["API", "Compute"]
    api, compute = dk2.services
    assert api.slug == "api"
    assert api.status == Status.OK
    assert compute.slug == "compute"
    assert compute.status == Status.MAJOR


def test_parse_zones_skips_malformed() -> None:
    assert parse_zones({"services": [None, {"name": "NoChildren"}]}) == ()
    assert parse_zones({}) == ()
    assert parse_zones({"services": [{"name": "Z", "children": "oops"}]}) == ()


def test_parse_notices(summary_payload: dict[str, object]) -> None:
    incidents, maintenances = parse_notices(summary_payload)
    assert [i.title for i in incidents] == ["Compute outage in CH-DK-2"]
    assert incidents[0].notice_type == "incident"
    assert incidents[0].lifecycle == "active"
    assert incidents[0].severity == "major"
    assert incidents[0].starts_at == "2026-01-02T10:00:00Z"
    # description comes from the latest update
    assert incidents[0].description == "We have identified the issue."
    assert {m.title for m in maintenances} == {
        "SOS maintenance window", "SKS patching in progress"}
    assert all(m.notice_type == "maintenance" for m in maintenances)
    assert all(m.lifecycle == "pending" for m in maintenances)


def test_parse_notices_description_fallbacks() -> None:
    payload: dict[str, object] = {
        "incidents": [{"id": 1, "title": "Only a title"}],
        "maintenances": [
            {"id": 2, "title": "With description", "description": "<p>The body</p>"},
        ],
    }
    incidents, maintenances = parse_notices(payload)
    assert incidents[0].description == "Only a title"
    assert maintenances[0].description == "The body"
    assert maintenances[0].severity is None


def test_parse_notices_missing_data() -> None:
    assert parse_notices({}) == ((), ())
    assert parse_notices({"incidents": None, "maintenances": "oops"}) == ((), ())
    assert parse_notices({"incidents": [{"id": 1}, {"title": "NoId"}]}) == ((), ())


def test_parse_notices_returns_immutable_tuples() -> None:
    incidents, maintenances = parse_notices({"incidents": [], "maintenances": []})
    assert isinstance(incidents, tuple)
    assert isinstance(maintenances, tuple)
    assert (incidents, maintenances) == ((), ())
    assert all(isinstance(n, Notice) for n in incidents + maintenances)


def test_to_plain_text() -> None:
    assert to_plain_text("<p>hello <b>world</b></p>") == "hello world"
    assert to_plain_text("a  b\n\tc") == "a b c"
    assert to_plain_text(None) == ""
