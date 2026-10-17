"""Tests for lib.statuspal_client (TDD) - no real network."""
from __future__ import annotations

import pytest
import requests
from lib.configuration import AppConfig
from lib.statuspal_client import StatusPalClient, StatusPalError


class FakeResponse:
    """An HttpResponse test double."""

    def __init__(
        self,
        payload: object = None,
        status_code: int = 200,
        json_error: bool = False,
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self._json_error = json_error

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> object:
        if self._json_error:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    """An HttpSession test double recording every call."""

    def __init__(
        self,
        responses: dict[str, FakeResponse] | None = None,
        fail_first: int = 0,
    ) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.fail_first = fail_first

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((url, dict(kwargs)))
        key = url.split("/api/v2/")[-1]
        if len(self.calls) <= self.fail_first:
            raise requests.ConnectionError("boom")
        return self.responses.get(key, FakeResponse({"services": []}))


def make_config() -> AppConfig:
    return AppConfig(
        statuspal_base_url="https://statuspal.eu/api/v2",
        status_page_subdomain="exoscalestatus",
        request_timeout_seconds=1.0,
        cache_ttl_seconds=1.0,
        log_level="INFO",
        app_name="Exoscale",
        app_logo="17776",
        status_icons={"up": "1", "down-minor": "2", "down-major": "3",
                      "down-fire": "4", "scheduled": "5", "no-status": "6", "tool": "7"},
        rate_limit_per_minute=120,
    )


def make_session(summary: object) -> FakeSession:
    return FakeSession(
        {"status_pages/exoscalestatus/summary": FakeResponse(summary)},
    )


def _headers(call: tuple[str, dict[str, object]]) -> dict[str, str]:
    headers = call[1]["headers"]
    assert isinstance(headers, dict)
    return {str(key): str(value) for key, value in headers.items()}


def test_fetch_success_sends_user_agent_and_parses(summary_payload: dict[str, object]) -> None:
    session = make_session(summary_payload)
    client = StatusPalClient(make_config(), session=session)
    data = client.fetch_status_data()
    # a single public v2 summary request
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url.endswith("/status_pages/exoscalestatus/summary")
    headers = _headers(session.calls[0])
    assert "Authorization" not in headers
    assert "lametric-exoscale-status" in headers["User-Agent"]
    assert kwargs["timeout"] == 1.0
    assert data.page_status.value == "degraded"
    assert len(data.services) == 4
    assert len(data.zones) == 3
    assert len(data.incidents) == 1
    assert len(data.maintenances) == 2
    assert data.fetched_at is not None
    assert data.errors == ()


def test_fetch_never_sends_authorization_header(summary_payload: dict[str, object]) -> None:
    session = make_session(summary_payload)
    client = StatusPalClient(make_config(), session=session)
    data = client.fetch_status_data()
    headers = _headers(session.calls[0])
    assert "Authorization" not in headers
    assert "lametric-exoscale-status" in headers["User-Agent"]
    assert data.page_status.value == "degraded"


def test_http_error_raises(summary_payload: dict[str, object]) -> None:
    session = make_session(summary_payload)
    session.responses["status_pages/exoscalestatus/summary"] = FakeResponse(status_code=500)
    with pytest.raises(StatusPalError):
        StatusPalClient(make_config(), session=session).fetch_status_data()


def test_retries_then_succeeds(summary_payload: dict[str, object]) -> None:
    session = make_session(summary_payload)
    session.fail_first = 1  # first call raises ConnectionError
    client = StatusPalClient(make_config(), session=session)
    data = client.fetch_status_data()
    assert data.page_status.value == "degraded"
    assert len(session.calls) == 2  # 1 + 1 retry


def test_bad_json_raises(summary_payload: dict[str, object]) -> None:
    session = make_session(summary_payload)
    session.responses["status_pages/exoscalestatus/summary"] = FakeResponse(json_error=True)
    with pytest.raises(StatusPalError):
        StatusPalClient(make_config(), session=session).fetch_status_data()


def test_persistent_timeout_raises(summary_payload: dict[str, object]) -> None:
    session = make_session(summary_payload)
    session.fail_first = 99
    with pytest.raises(StatusPalError):
        StatusPalClient(make_config(), session=session, max_retries=1).fetch_status_data()
