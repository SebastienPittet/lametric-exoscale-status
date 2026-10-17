"""HTTP client for the public StatusPal API (v2).

The status page is public open data: no authentication is required and
no credentials are ever sent.

The client depends on a narrow session protocol (``HttpSession``) rather
than on ``requests.Session`` directly, so it is testable with fakes that
are type-checked.
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Protocol

import requests

from lib.configuration import AppConfig
from lib.models import StatusData
from lib.statuspal_parser import (
    parse_notices,
    parse_services,
    parse_status_page,
    parse_zones,
)

logger = logging.getLogger(__name__)

USER_AGENT = "lametric-exoscale-status/2.0"

#: Headers sent on every request: identifies this client to the upstream API.
HEADERS: dict[str, str] = {"User-Agent": USER_AGENT}

_BACKOFF_BASE_SECONDS = 0.1


class HttpResponse(Protocol):
    """The part of an HTTP response this client uses."""

    def raise_for_status(self) -> None:
        """Raise on a 4xx/5xx status code."""
        ...

    def json(self) -> object:
        """Decode the body as JSON (arbitrary JSON value)."""
        ...


class HttpSession(Protocol):
    """The part of an HTTP session this client uses."""

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> HttpResponse:
        """Perform a GET request and return the response."""
        ...


class StatusPalError(Exception):
    """Raised when the StatusPal API is unreachable or returns bad data."""


class StatusPalClient:
    """Fetch the Exoscale status page from the public StatusPal API (v2)."""

    def __init__(
        self,
        config: AppConfig,
        session: HttpSession | None = None,
        max_retries: int = 2,
    ) -> None:
        self._config = config
        self._session: HttpSession = session if session is not None else requests.Session()
        self._max_retries = max_retries

    def _get(self, url: str) -> dict[str, object]:
        """GET a JSON object payload, retrying with a short backoff.

        Raises StatusPalError after the final failed attempt.
        """
        attempts = self._max_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self._session.get(
                    url,
                    headers=HEADERS,
                    timeout=self._config.request_timeout_seconds,
                )
                response.raise_for_status()
                payload: object = response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "StatusPal request failed: %s (%s) [attempt %d/%d]",
                    url,
                    exc,
                    attempt + 1,
                    attempts,
                )
                if attempt < self._max_retries:
                    time.sleep(_BACKOFF_BASE_SECONDS * (2**attempt))
                continue
            if not isinstance(payload, dict):
                last_error = ValueError("response is not a JSON object")
                logger.warning(
                    "StatusPal response is not a JSON object: %s [attempt %d/%d]",
                    url,
                    attempt + 1,
                    attempts,
                )
                if attempt < self._max_retries:
                    time.sleep(_BACKOFF_BASE_SECONDS * (2**attempt))
                continue
            return payload
        raise StatusPalError(
            f"StatusPal request to {url} failed after {attempts} attempts"
        ) from last_error

    def fetch_status_data(self) -> StatusData:
        """Fetch the public v2 summary and assemble a StatusData snapshot.

        A single request returns the page status, services, zones,
        incidents and maintenances. Raises StatusPalError if the request
        fails after retries; partial data is never returned.
        """
        url = (
            f"{self._config.statuspal_base_url}"
            f"/status_pages/{self._config.status_page_subdomain}/summary"
        )
        payload = self._get(url)
        incidents, maintenances = parse_notices(payload)
        return StatusData(
            page_status=parse_status_page(payload),
            services=parse_services(payload),
            zones=parse_zones(payload),
            incidents=incidents,
            maintenances=maintenances,
            fetched_at=datetime.now(UTC),
        )
