"""Parsers that turn StatusPal "next" API (v1) payloads into domain models."""
from __future__ import annotations

import re
from typing import Any

from lib.models import Notice, Service, Status, Zone, ZoneService

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

_PAGE_STATUSES = {"operational", "degraded", "unavailable"}


def to_plain_text(html: str | None) -> str:
    """Strip HTML tags and collapse whitespace into a single-line text."""
    if html is None:
        return ""
    text = _TAG_RE.sub(" ", str(html))
    return _WHITESPACE_RE.sub(" ", text).strip()


def status_from_value(value: Any) -> Status:
    """Map a raw status value to a Status (unknown values map to UNKNOWN)."""
    if value is None or value == "":
        return Status.OK
    try:
        return Status(str(value).lower())
    except ValueError:
        return Status.UNKNOWN


def _data_list(payload: Any) -> list:
    """Return payload["data"] when it is a list, else an empty list."""
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, list) else []


def parse_status_page(payload: Any) -> str:
    """Return the page status, or "unknown" when it cannot be determined."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return "unknown"
    current = data.get("current_status")
    return current if current in _PAGE_STATUSES else "unknown"


def parse_services(payload: Any) -> tuple[Service, ...]:
    """Parse the /services endpoint payload into Service objects."""
    services: list[Service] = []
    for item in _data_list(payload):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name:
            continue
        containers = item.get("containers") or []
        services.append(
            Service(
                id=str(item.get("id") or ""),
                slug=str(item.get("slug") or ""),
                name=str(name),
                status=status_from_value(item.get("status")),
                scope=str(item.get("scope") or "global"),
                containers=tuple(str(container) for container in containers),
            )
        )
    return tuple(services)


def parse_zones(payload: Any) -> tuple[Zone, ...]:
    """Parse the /containers endpoint payload into Zone objects."""
    zones: list[Zone] = []
    for item in _data_list(payload):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        slug = item.get("slug")
        if not name or not slug:
            continue
        services: list[ZoneService] = []
        for entry in item.get("services") or []:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            services.append(
                ZoneService(
                    slug=str(entry.get("slug", "")),
                    name=str(entry.get("name")),
                    status=status_from_value(entry.get("status")),
                )
            )
        zones.append(
            Zone(
                id=str(item.get("id", "")),
                slug=str(slug),
                name=str(name),
                services=tuple(services),
            )
        )
    return tuple(zones)


def parse_notices(payload: Any) -> tuple[list[Notice], list[Notice]]:
    """Split notices into active incidents and pending/active maintenances.

    Incidents: notice_type == "incident" and lifecycle != "completed".
    Maintenances: notice_type == "maintenance" and lifecycle in pending/active.
    Info notices are ignored; entries without id or title are skipped.
    """
    incidents: list[Notice] = []
    maintenances: list[Notice] = []
    for item in _data_list(payload):
        if not isinstance(item, dict):
            continue
        notice_id = item.get("id")
        title = item.get("title")
        if not notice_id or not title:
            continue
        notice_type = str(item.get("notice_type", "")).lower()
        lifecycle = str(item.get("lifecycle", "")).lower()
        if notice_type == "incident" and lifecycle != "completed":
            bucket = incidents
        elif notice_type == "maintenance" and lifecycle in {"pending", "active"}:
            bucket = maintenances
        else:
            continue
        latest_update = item.get("latest_update")
        body = latest_update.get("body") if isinstance(latest_update, dict) else None
        bucket.append(
            Notice(
                id=str(notice_id),
                notice_type=notice_type,
                title=str(title),
                status=str(item.get("status") or ""),
                severity=item.get("severity"),
                lifecycle=lifecycle,
                starts_at=item.get("starts_at"),
                ends_at=item.get("ends_at"),
                description=to_plain_text(body),
            )
        )
    return incidents, maintenances
