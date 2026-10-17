"""HTTP client for the StatusPal "next" API (v1).

The API key is sent as a Bearer token and must never be logged.
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
NOTICES_PER_PAGE = 100


class StatusPalError(Exception):
    """Raised when the StatusPal API is unreachable or returns bad data."""


class StatusPalClient:
    """Fetch the Exoscale status page from the StatusPal API."""

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
        return {
            "Authorization": f"Bearer {self._config.statuspal_api_key}",
            "User-Agent": USER_AGENT,
        }

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
        """Fetch page, services, zones and notices, assembled as StatusData.

        Raises StatusPalError if any request fails after retries; partial
        data is never returned.
        """
        base = (
            f"{self._config.statuspal_base_url}"
            f"/status_pages/{self._config.status_page_subdomain}"
        )
        page = self._get(base)
        services = self._get(f"{base}/services")
        containers = self._get(f"{base}/containers")
        notices = self._get(f"{base}/notices", params={"per_page": NOTICES_PER_PAGE})
        incidents, maintenances = parse_notices(notices)
        return StatusData(
            page_status=parse_status_page(page),
            services=parse_services(services),
            zones=parse_zones(containers),
            incidents=tuple(incidents),
            maintenances=tuple(maintenances),
            fetched_at=datetime.now(timezone.utc),
            errors=(),
        )
