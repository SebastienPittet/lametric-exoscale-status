"""Flask application exposing the Exoscale status to LAMETRIC Time clocks."""
from __future__ import annotations

import logging

from flask import Flask, Response, jsonify, request
from lib.cache import CachedFetch, TtlCache
from lib.configuration import AppConfig, load_config
from lib.frames import build_frames
from lib.models import Notice, PageStatus, Status, StatusData, StatusDataProvider
from lib.security import SECURITY_HEADERS, RateLimiter
from lib.statuspal_client import StatusPalClient, StatusPalError
from lib.subscription import Subscription, SubscriptionError, parse_subscription

logger = logging.getLogger(__name__)

APP_NAME = "lametric-exoscale-status"
APP_VERSION = "2.0.0"

_ENDPOINTS: list[str] = [
    "/",
    "/healthz",
    "/api/v1/",
    "/api/v1/status",
    "/api/v1/zones",
    "/api/v1/services",
    "/api/v1/incidents",
    "/api/v1/maintenances",
]

#: Return type of the JSON endpoint handlers.
JsonResult = Response | tuple[Response, int]


_LOG_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def _ensure_logging(level: str) -> None:
    """Install a basic logging setup when none is configured yet."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=_LOG_LEVELS.get(level, logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )


def _unavailable_status_data() -> StatusData:
    """Fallback snapshot used when the upstream API is down."""
    return StatusData(
        page_status=PageStatus.UNKNOWN,
        services=(),
        zones=(),
        incidents=(),
        maintenances=(),
        fetched_at=None,
    )


def _notice_dict(notice: Notice) -> dict[str, object]:
    """JSON-safe representation of a notice (enum values, not enum objects)."""
    return {
        "id": notice.id,
        "title": notice.title,
        "status": notice.status.value,
        "severity": notice.severity,
        "lifecycle": notice.lifecycle.value,
        "starts_at": notice.starts_at,
        "ends_at": notice.ends_at,
        "description": notice.description,
    }


def create_app(
    config: AppConfig | None = None,
    client: StatusDataProvider | None = None,
) -> Flask:
    """Application factory for the LAMETRIC status API."""
    if config is None:
        config = load_config()
    if client is None:
        client = StatusPalClient(config)
    _ensure_logging(config.log_level)

    app = Flask(__name__)
    limiter = RateLimiter(config.rate_limit_per_minute)
    cache = TtlCache[StatusData](config.cache_ttl_seconds)
    fetcher = CachedFetch[StatusData](client.fetch_status_data, cache, key="status")

    @app.before_request
    def enforce_rate_limit() -> Response | tuple[Response, int] | None:
        if not limiter.hit(request.remote_addr or "unknown"):
            return (
                jsonify({"error": "rate limit exceeded", "retry_after_seconds": 60}),
                429,
            )
        return None

    @app.after_request
    def apply_security_headers(response: Response) -> Response:
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
    def index() -> JsonResult:
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
    def healthz() -> JsonResult:
        return jsonify({"status": "ok"})

    @app.route("/api/v1/")
    def lametric_frames() -> JsonResult:
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
    def status_view() -> JsonResult:
        data = load_data_or_503()
        if data is None:
            return jsonify({"error": "upstream_unavailable"}), 503
        impacted = sum(
            1
            for zone in data.zones
            for service in zone.services
            if service.status is not Status.OK
        )
        return jsonify(
            {
                "current_status": data.page_status.value,
                "fetched_at": data.fetched_at.isoformat() if data.fetched_at else None,
                "impacted_services": impacted,
                "active_incidents": len(data.incidents),
                "maintenances": len(data.maintenances),
            }
        )

    @app.route("/api/v1/zones")
    def zones_view() -> JsonResult:
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
    def services_view() -> JsonResult:
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
                    }
                    for service in data.services
                ]
            }
        )

    @app.route("/api/v1/incidents")
    def incidents_view() -> JsonResult:
        data = load_data_or_503()
        if data is None:
            return jsonify({"error": "upstream_unavailable"}), 503
        return jsonify({"incidents": [_notice_dict(n) for n in data.incidents]})

    @app.route("/api/v1/maintenances")
    def maintenances_view() -> JsonResult:
        data = load_data_or_503()
        if data is None:
            return jsonify({"error": "upstream_unavailable"}), 503
        return jsonify({"maintenances": [_notice_dict(n) for n in data.maintenances]})

    @app.errorhandler(404)
    def handle_not_found(_error: Exception) -> JsonResult:
        return jsonify({"error": "not_found"}), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(_error: Exception) -> JsonResult:
        return jsonify({"error": "method_not_allowed"}), 405

    @app.errorhandler(500)
    def handle_internal_error(_error: Exception) -> JsonResult:
        return jsonify({"error": "internal_server_error"}), 500

    return app


app = create_app()


if __name__ == "__main__":
    app.run()
