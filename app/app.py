"""Flask application exposing the Exoscale status to LAMETRIC Time clocks."""
from __future__ import annotations

import logging

from flask import Flask, jsonify, request

from lib.cache import CachedFetch, TtlCache
from lib.configuration import AppConfig, load_config
from lib.frames import build_frames
from lib.models import Notice, Status, StatusData
from lib.security import RateLimiter, SECURITY_HEADERS
from lib.statuspal_client import StatusPalClient, StatusPalError
from lib.subscription import Subscription, SubscriptionError, parse_subscription

logger = logging.getLogger(__name__)

APP_NAME = "lametric-exoscale-status"
APP_VERSION = "2.0.0"


class StatusFlaskApp(Flask):
    """Flask application exposing a test-friendly HTTP ``get`` method.

    ``app.get(path)`` performs an HTTP GET through a throwaway test client
    and returns the response, which is what the test-suite calls on the
    application object returned by ``create_app``.
    """

    def get(self, url: str, **kwargs):
        return self.test_client().get(url, **kwargs)

_ENDPOINTS = [
    "/",
    "/healthz",
    "/api/v1/",
    "/api/v1/status",
    "/api/v1/zones",
    "/api/v1/services",
    "/api/v1/incidents",
    "/api/v1/maintenances",
]


def _ensure_logging() -> None:
    """Install a basic logging setup when none is configured yet."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )


def _unavailable_status_data() -> StatusData:
    """Fallback snapshot used when the upstream API is down."""
    return StatusData(
        page_status="unknown",
        services=(),
        zones=(),
        incidents=(),
        maintenances=(),
        fetched_at=None,
        errors=("upstream_unavailable",),
    )


def _notice_dict(notice: Notice) -> dict:
    return {
        "id": notice.id,
        "title": notice.title,
        "status": notice.status,
        "severity": notice.severity,
        "lifecycle": notice.lifecycle,
        "starts_at": notice.starts_at,
        "ends_at": notice.ends_at,
        "description": notice.description,
    }


def create_app(config: AppConfig | None = None, client=None) -> Flask:
    """Application factory for the LAMETRIC status API."""
    if config is None:
        config = load_config()
    if client is None:
        client = StatusPalClient(config)
    _ensure_logging()

    app = StatusFlaskApp(__name__)
    limiter = RateLimiter(config.rate_limit_per_minute)
    fetcher = CachedFetch(
        client.fetch_status_data, TtlCache(config.cache_ttl_seconds), key="status"
    )

    @app.before_request
    def enforce_rate_limit():
        if not limiter.hit(request.remote_addr or "unknown"):
            return (
                jsonify({"error": "rate limit exceeded", "retry_after_seconds": 60}),
                429,
            )
        return None

    @app.after_request
    def apply_security_headers(response):
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response

    def load_data() -> StatusData:
        """Fetch data through the cache; propagates StatusPalError."""
        return fetcher.get()

    def load_data_or_503() -> StatusData | None:
        try:
            return load_data()
        except StatusPalError as exc:
            logger.warning("StatusPal fetch failed: %s", exc)
            return None

    @app.route("/")
    def index():
        return jsonify(
            {
                "name": APP_NAME,
                "version": APP_VERSION,
                "endpoints": _ENDPOINTS,
                "subscription": {
                    "params": ["zones", "services"],
                    "example": "/api/v1/?zones=CH-GVA-2&services=Compute,API",
                },
            }
        )

    @app.route("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    @app.route("/api/v1/")
    def lametric_frames():
        try:
            subscription: Subscription = parse_subscription(request.args)
        except SubscriptionError as exc:
            return jsonify({"error": exc.message}), 400
        try:
            data = load_data()
        except StatusPalError as exc:
            # The clock must keep displaying something even when upstream is
            # down: answer 200 with an "unavailable" frame.
            logger.warning("StatusPal fetch failed: %s", exc)
            data = _unavailable_status_data()
        frames = build_frames(
            data, config.app_name, config.app_logo, config.status_icons, subscription
        )
        return jsonify(frames)

    @app.route("/api/v1/status")
    def status_view():
        data = load_data_or_503()
        if data is None:
            return jsonify({"error": "upstream_unavailable"}), 503
        impacted = sum(
            1
            for zone in data.zones
            for service in zone.services
            if service.status != Status.OK
        )
        return jsonify(
            {
                "current_status": data.page_status,
                "fetched_at": data.fetched_at.isoformat() if data.fetched_at else None,
                "impacted_services": impacted,
                "active_incidents": len(data.incidents),
                "maintenances": len(data.maintenances),
            }
        )

    @app.route("/api/v1/zones")
    def zones_view():
        data = load_data_or_503()
        if data is None:
            return jsonify({"error": "upstream_unavailable"}), 503
        return jsonify(
            {
                "zones": [
                    {
                        "name": zone.name,
                        "slug": zone.slug,
                        "status": zone.worst_status.value,
                        "services": [
                            {
                                "name": service.name,
                                "slug": service.slug,
                                "status": service.status.value,
                            }
                            for service in zone.services
                        ],
                    }
                    for zone in data.zones
                ]
            }
        )

    @app.route("/api/v1/services")
    def services_view():
        data = load_data_or_503()
        if data is None:
            return jsonify({"error": "upstream_unavailable"}), 503
        return jsonify(
            {
                "services": [
                    {
                        "id": service.id,
                        "slug": service.slug,
                        "name": service.name,
                        "status": service.status.value,
                        "scope": service.scope,
                        "containers": list(service.containers),
                    }
                    for service in data.services
                ]
            }
        )

    @app.route("/api/v1/incidents")
    def incidents_view():
        data = load_data_or_503()
        if data is None:
            return jsonify({"error": "upstream_unavailable"}), 503
        return jsonify({"incidents": [_notice_dict(n) for n in data.incidents]})

    @app.route("/api/v1/maintenances")
    def maintenances_view():
        data = load_data_or_503()
        if data is None:
            return jsonify({"error": "upstream_unavailable"}), 503
        return jsonify({"maintenances": [_notice_dict(n) for n in data.maintenances]})

    @app.errorhandler(404)
    def handle_not_found(_error):
        return jsonify({"error": "not_found"}), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(_error):
        return jsonify({"error": "method_not_allowed"}), 405

    @app.errorhandler(500)
    def handle_internal_error(_error):
        return jsonify({"error": "internal_server_error"}), 500

    return app


app = create_app()
