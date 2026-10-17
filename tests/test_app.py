"""Tests for app routes (TDD)."""
import dataclasses
from datetime import datetime, timezone

import pytest

from app import create_app
from lib.configuration import load_config
from lib.models import StatusData
from lib.statuspal_client import StatusPalError
from lib.statuspal_parser import (
    parse_notices,
    parse_status_page,
    parse_services,
    parse_zones,
)


class FakeClient:
    def __init__(self, data=None, error=None):
        self._data, self._error = data, error

    def fetch_status_data(self):
        if self._error:
            raise self._error
        return self._data


@pytest.fixture()
def data(summary_payload):
    incidents, maintenances = parse_notices(summary_payload)
    return StatusData(
        page_status=parse_status_page(summary_payload),
        services=parse_services(summary_payload),
        zones=parse_zones(summary_payload),
        incidents=tuple(incidents),
        maintenances=tuple(maintenances),
        fetched_at=datetime.now(timezone.utc),
        errors=(),
    )


@pytest.fixture()
def make_app(valid_config_toml, data):
    def _make(client_data=None, client_error=None, **replace_kw):
        cfg = dataclasses.replace(load_config(valid_config_toml), **replace_kw)
        client = FakeClient(data=client_data if client_data is not None else data,
                            error=client_error)
        return create_app(cfg, client=client)
    return _make


def _texts(response):
    return [f["text"] for f in response.get_json()["frames"]]


def test_root_lists_endpoints(make_app):
    resp = make_app().get("/")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "/api/v1/" in body["endpoints"]
    assert body["subscription"]["params"] == ["zones", "services"]


def test_healthz(make_app):
    assert make_app().get("/healthz").get_json() == {"status": "ok"}


def test_frames_endpoint(make_app):
    resp = make_app().get("/api/v1/")
    assert resp.status_code == 200
    texts = _texts(resp)
    assert texts[0] == "Exoscale"
    assert "CH-DK-2 Compute" in texts


def test_frames_subscription_zones(make_app):
    resp = make_app().get("/api/v1/?zones=ch-gva-2")
    texts = _texts(resp)
    assert "CH-GVA-2 API" in texts
    assert not any("CH-DK-2" in t for t in texts)


def test_frames_subscription_bad_value(make_app):
    resp = make_app().get("/api/v1/?zones=bad;name")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_status_endpoint(make_app):
    body = make_app().get("/api/v1/status").get_json()
    assert body["current_status"] == "degraded"
    assert body["active_incidents"] == 1
    assert body["maintenances"] == 2


def test_zones_endpoint(make_app):
    body = make_app().get("/api/v1/zones").get_json()
    assert len(body["zones"]) == 3
    assert {z["slug"] for z in body["zones"]} == {"ch-gva-2", "ch-dk-2", "de-fra-1"}


def test_services_endpoint(make_app):
    body = make_app().get("/api/v1/services").get_json()
    assert len(body["services"]) == 4


def test_incidents_endpoint(make_app):
    body = make_app().get("/api/v1/incidents").get_json()
    assert [i["title"] for i in body["incidents"]] == ["Compute outage in CH-DK-2"]


def test_maintenances_endpoint(make_app):
    body = make_app().get("/api/v1/maintenances").get_json()
    assert len(body["maintenances"]) == 2


def test_404_returns_json(make_app):
    resp = make_app().get("/nope")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"


def test_security_headers(make_app):
    resp = make_app().get("/healthz")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert resp.headers["Cache-Control"] == "no-store"


def test_upstream_down_lametric_shows_unavailable(make_app):
    app = make_app(client_error=StatusPalError("boom"))
    resp = app.get("/api/v1/")
    assert resp.status_code == 200
    assert _texts(resp)[-1] == "Status unavailable"


def test_upstream_down_json_endpoints_503(make_app):
    app = make_app(client_error=StatusPalError("boom"))
    assert app.get("/api/v1/status").status_code == 503
    assert app.get("/api/v1/zones").status_code == 503


def test_rate_limit(make_app):
    app = make_app(rate_limit_per_minute=2)
    assert app.get("/api/v1/").status_code == 200
    assert app.get("/api/v1/").status_code == 200
    resp = app.get("/api/v1/")
    assert resp.status_code == 429
    assert resp.get_json()["error"] == "rate limit exceeded"
