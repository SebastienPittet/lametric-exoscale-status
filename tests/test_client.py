"""Tests for lib.statuspal_client (TDD) - no real network."""
import pytest
import requests

from lib.configuration import AppConfig
from lib.statuspal_client import StatusPalClient, StatusPalError


class FakeResponse:
    def __init__(self, payload=None, status_code=200, json_error=False):
        self._payload = payload
        self.status_code = status_code
        self._json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self._json_error:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, responses=None, fail_first=0):
        self.responses = responses or {}
        self.calls = []
        self.fail_first = fail_first

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        key = url.split("/api/v2/")[-1]
        if len(self.calls) <= self.fail_first:
            raise requests.ConnectionError("boom")
        return self.responses.get(key, FakeResponse({"services": []}))


def make_config(**overrides):
    base = dict(
        statuspal_base_url="https://statuspal.eu/api/v2",
        status_page_subdomain="exoscalestatus",
        statuspal_api_key="secret",
        request_timeout_seconds=1.0,
        cache_ttl_seconds=1.0,
        app_name="Exoscale",
        app_logo="17776",
        status_icons={"up": "1", "down-minor": "2", "down-major": "3",
                      "down-fire": "4", "scheduled": "5", "no-status": "6", "tool": "7"},
        rate_limit_per_minute=120,
    )
    base.update(overrides)
    return AppConfig(**base)


def make_session(summary):
    return FakeSession({
        "status_pages/exoscalestatus/summary": FakeResponse(summary),
    })


def test_fetch_success_sends_auth_and_parses(summary_payload):
    session = make_session(summary_payload)
    client = StatusPalClient(make_config(), session=session)
    data = client.fetch_status_data()
    # a single public v2 summary request
    assert len(session.calls) == 1
    assert session.calls[0][0].endswith("/status_pages/exoscalestatus/summary")
    headers = session.calls[0][1]["headers"]
    assert headers["Authorization"] == "Bearer secret"
    assert "lametric-exoscale-status" in headers["User-Agent"]
    assert session.calls[0][1]["timeout"] == 1.0
    assert data.page_status == "degraded"
    assert len(data.services) == 4
    assert len(data.zones) == 3
    assert len(data.incidents) == 1
    assert len(data.maintenances) == 2
    assert data.fetched_at is not None
    assert data.errors == ()


def test_fetch_without_key_omits_authorization_header(summary_payload):
    session = make_session(summary_payload)
    client = StatusPalClient(make_config(statuspal_api_key=""), session=session)
    data = client.fetch_status_data()
    headers = session.calls[0][1]["headers"]
    assert "Authorization" not in headers
    assert "lametric-exoscale-status" in headers["User-Agent"]
    assert data.page_status == "degraded"


def test_http_error_raises(summary_payload):
    session = make_session(summary_payload)
    session.responses["status_pages/exoscalestatus/summary"] = FakeResponse(status_code=500)
    with pytest.raises(StatusPalError):
        StatusPalClient(make_config(), session=session).fetch_status_data()


def test_retries_then_succeeds(summary_payload):
    session = make_session(summary_payload)
    session.fail_first = 1  # first call raises ConnectionError
    client = StatusPalClient(make_config(), session=session)
    data = client.fetch_status_data()
    assert data.page_status == "degraded"
    assert len(session.calls) == 2  # 1 + 1 retry


def test_bad_json_raises(summary_payload):
    session = make_session(summary_payload)
    session.responses["status_pages/exoscalestatus/summary"] = FakeResponse(json_error=True)
    with pytest.raises(StatusPalError):
        StatusPalClient(make_config(), session=session).fetch_status_data()


def test_persistent_timeout_raises(summary_payload):
    session = make_session(summary_payload)
    session.fail_first = 99
    with pytest.raises(StatusPalError):
        StatusPalClient(make_config(), session=session, max_retries=1).fetch_status_data()
