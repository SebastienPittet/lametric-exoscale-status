"""HTTP client for the public StatusPal API (v2).

The status page is public open data: no authentication is required.
When an API key is configured (STATUSPAL_API_KEY environment variable),
it is sent as a Bearer token; it must never be logged.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

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
_BACKOFF_BASE_SECONDS = 0.1


class StatusPalError(Exception):
    """Raised when the StatusPal API is unreachable or returns bad data."""


class StatusPalClient:
    """Fetch the Exoscale status page from the public StatusPal API (v2)."""

    def __init__(
        self,
        config: AppConfig,
        session: requests.Session | None = None,
        max_retries: int = 2,
    ) -> None:
        self._config = config
        self._session = session if session is not None else requests.Session()
        self._max_retries = max_retries

    def _headers(self) -> dict[str, str]:
        """Build the request headers.

        The Authorization header is only added when an API key is set;
        the public API works without it.
        """
        headers = {"User-Agent": USER_AGENT}
        api_key = self._config.statuspal_api_key
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _get(self, url: str, **kwargs) -> dict:
        """GET a JSON object payload, retrying with a short backoff.

        Raises StatusPalError after the final failed attempt.
        """
        attempts = self._max_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self._session.get(
                    url,
                    headers=self._headers(),
                    timeout=self._config.request_timeout_seconds,
                    **kwargs,
                )
                response.raise_for_status()
                payload = response.json()
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
            incidents=tuple(incidents),
            maintenances=tuple(maintenances),
            fetched_at=datetime.now(timezone.utc),
            errors=(),
        )
