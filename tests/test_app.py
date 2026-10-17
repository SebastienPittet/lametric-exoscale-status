"""Tests for app routes (TDD)."""
from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from flask import Flask
from lib.configuration import load_config
from lib.models import StatusData
from lib.statuspal_client import StatusPalError
from lib.statuspal_parser import (
    parse_notices,
    parse_services,
    parse_status_page,
    parse_zones,
)
from werkzeug.wrappers import Response

from app import create_app


class FakeClient:
    """A StatusDataProvider test double."""

    def __init__(
        self,
        data: StatusData | None = None,
        error: StatusPalError | None = None,
    ) -> None:
        self._data = data
        self._error = error

    def fetch_status_data(self) -> StatusData:
        if self._error is not None:
            raise self._error
        assert self._data is not None, "FakeClient configured without data"
        return self._data


@pytest.fixture()
def data(summary_payload: dict[str, object]) -> StatusData:
    incidents, maintenances = parse_notices(summary_payload)
    return StatusData(
        page_status=parse_status_page(summary_payload),
        services=parse_services(summary_payload),
        zones=parse_zones(summary_payload),
        incidents=incidents,
        maintenances=maintenances,
        fetched_at=datetime.now(UTC),
    )


@pytest.fixture()
def make_app(
    valid_config_toml: Path, data: StatusData
) -> Callable[..., Flask]:
    def _make(
        client_data: StatusData | None = None,
        client_error: StatusPalError | None = None,
        rate_limit_per_minute: int | None = None,
    ) -> Flask:
        base = load_config(valid_config_toml)
        if rate_limit_per_minute is not None:
            base = dataclasses.replace(
                base, rate_limit_per_minute=rate_limit_per_minute
            )
        client = FakeClient(
            data=client_data if client_data is not None else data,
            error=client_error,
        )
        return create_app(base, client=client)

    return _make


def _texts(response: Response) -> list[str]:
    frames: list[dict[str, str]] = response.get_json()["frames"]
    return [frame["text"] for frame in frames]


def test_root_lists_endpoints(make_app: Callable[..., Flask]) -> None:
    resp = make_app().test_client().get("/")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "/api/v1/" in body["endpoints"]
    assert body["subscription"]["params"] == ["zones", "services"]


def test_healthz(make_app: Callable[..., Flask]) -> None:
    assert make_app().test_client().get("/healthz").get_json() == {"status": "ok"}


def test_frames_endpoint(make_app: Callable[..., Flask]) -> None:
    resp = make_app().test_client().get("/api/v1/")
    assert resp.status_code == 200
    texts = _texts(resp)
    assert texts[0] == "Exoscale"
    assert "CH-DK-2 Compute" in texts


def test_frames_subscription_zones(make_app: Callable[..., Flask]) -> None:
    resp = make_app().test_client().get("/api/v1/?zones=ch-gva-2")
    texts = _texts(resp)
    assert "CH-GVA-2 API" in texts
    assert not any("CH-DK-2" in t for t in texts)


def test_frames_subscription_bad_value(make_app: Callable[..., Flask]) -> None:
    resp = make_app().test_client().get("/api/v1/?zones=bad;name")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_status_endpoint(make_app: Callable[..., Flask]) -> None:
    body = make_app().test_client().get("/api/v1/status").get_json()
    assert body["current_status"] == "degraded"
    assert body["active_incidents"] == 1
    assert body["maintenances"] == 2


def test_zones_endpoint(make_app: Callable[..., Flask]) -> None:
    body = make_app().test_client().get("/api/v1/zones").get_json()
    assert len(body["zones"]) == 3
    assert {z["slug"] for z in body["zones"]} == {"ch-gva-2", "ch-dk-2", "de-fra-1"}


def test_services_endpoint(make_app: Callable[..., Flask]) -> None:
    body = make_app().test_client().get("/api/v1/services").get_json()
    assert len(body["services"]) == 4


def test_incidents_endpoint(make_app: Callable[..., Flask]) -> None:
    body = make_app().test_client().get("/api/v1/incidents").get_json()
    assert [i["title"] for i in body["incidents"]] == ["Compute outage in CH-DK-2"]


def test_maintenances_endpoint(make_app: Callable[..., Flask]) -> None:
    body = make_app().test_client().get("/api/v1/maintenances").get_json()
    assert len(body["maintenances"]) == 2


def test_404_returns_json(make_app: Callable[..., Flask]) -> None:
    resp = make_app().test_client().get("/nope")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "not_found"


def test_security_headers(make_app: Callable[..., Flask]) -> None:
    resp = make_app().test_client().get("/healthz")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert resp.headers["Cache-Control"] == "no-store"


def test_upstream_down_lametric_shows_unavailable(make_app: Callable[..., Flask]) -> None:
    app = make_app(client_error=StatusPalError("boom"))
    resp = app.test_client().get("/api/v1/")
    assert resp.status_code == 200
    assert _texts(resp)[-1] == "Status unavailable"


def test_upstream_down_json_endpoints_503(make_app: Callable[..., Flask]) -> None:
    app = make_app(client_error=StatusPalError("boom"))
    assert app.test_client().get("/api/v1/status").status_code == 503
    assert app.test_client().get("/api/v1/zones").status_code == 503


def test_rate_limit(make_app: Callable[..., Flask]) -> None:
    app = make_app(rate_limit_per_minute=2)
    assert app.test_client().get("/api/v1/").status_code == 200
    assert app.test_client().get("/api/v1/").status_code == 200
    resp = app.test_client().get("/api/v1/")
    assert resp.status_code == 429
    assert resp.get_json()["error"] == "rate limit exceeded"
