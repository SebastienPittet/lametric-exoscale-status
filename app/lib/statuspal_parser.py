"""Parsers that turn the public StatusPal API v2 summary payload into domain models.

The v2 summary (``/api/v2/status_pages/{subdomain}/summary``) is a single
public JSON document:

- ``services``: top-level entries; entries with ``children`` are zones
  (each child is a zone service), entries without children are global
  services;
- ``status_page``: page metadata, including ``current_incident_type``;
- ``incidents`` / ``maintenances``: active incidents and maintenances.
"""
from __future__ import annotations

import re
from typing import Any

from lib.models import Notice, Service, Status, Zone, ZoneService

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

#: Mapping of StatusPal v2 incident types to a service Status.
_INCIDENT_TYPE_TO_STATUS = {
    "none": Status.OK,
    "ok": Status.OK,
    "operational": Status.OK,
    "minor": Status.MINOR,
    "major": Status.MAJOR,
    "critical": Status.CRITICAL,
    "maintenance": Status.MAINTENANCE,
    "scheduled": Status.MAINTENANCE,
}

#: Mapping of StatusPal v2 incident types to the page status string.
_INCIDENT_TYPE_TO_PAGE_STATUS = {
    "none": "operational",
    "ok": "operational",
    "operational": "operational",
    "minor": "degraded",
    "major": "unavailable",
    "critical": "unavailable",
}


def to_plain_text(html: str | None) -> str:
    """Strip HTML tags and collapse whitespace into a single-line text."""
    if html is None:
        return ""
    text = _TAG_RE.sub(" ", str(html))
    return _WHITESPACE_RE.sub(" ", text).strip()


def status_from_value(value: Any) -> Status:
    """Map a raw StatusPal v2 incident type to a Status.

    ``None``/empty mean "no incident" and map to OK; unknown values map
    to UNKNOWN.
    """
    if value is None:
        return Status.OK
    key = str(value).strip().lower()
    if not key:
        return Status.OK
    return _INCIDENT_TYPE_TO_STATUS.get(key, Status.UNKNOWN)


def page_status_from_value(value: Any) -> str:
    """Map a raw StatusPal v2 incident type to the page status string.

    ``None``/empty/"none" mean "no incident" -> "operational"; minor ->
    "degraded"; major/critical -> "unavailable"; unknown values -> "unknown".
    """
    if value is None:
        return "operational"
    key = str(value).strip().lower()
    if key in ("", "none"):
        return "operational"
    return _INCIDENT_TYPE_TO_PAGE_STATUS.get(key, "unknown")


def _slugify(name: str) -> str:
    """Derive a slug from a display name (lowercase, ``-`` separators)."""
    slug = _WHITESPACE_RE.sub("-", str(name).strip().lower())
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    return slug.strip("-")


def _services_list(payload: Any) -> list:
    """Return payload["services"] when it is a list, else an empty list."""
    services = payload.get("services") if isinstance(payload, dict) else None
    return services if isinstance(services, list) else []


def _item_list(payload: Any, key: str) -> list:
    """Return payload[key] when it is a list, else an empty list."""
    items = payload.get(key) if isinstance(payload, dict) else None
    return items if isinstance(items, list) else []


def parse_status_page(payload: Any) -> str:
    """Return the page status derived from the v2 summary payload.

    "unknown" is returned when no ``status_page`` block can be found.
    """
    page = payload.get("status_page") if isinstance(payload, dict) else None
    if not isinstance(page, dict):
        return "unknown"
    return page_status_from_value(page.get("current_incident_type"))


def parse_services(payload: Any) -> tuple[Service, ...]:
    """Parse the global (children-less) services of the v2 summary payload."""
    services: list[Service] = []
    for item in _services_list(payload):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name or item.get("children"):
            continue
        services.append(
            Service(
                id=str(item.get("id") or ""),
                slug=_slugify(str(name)),
                name=str(name),
                status=status_from_value(item.get("current_incident_type")),
                scope="global",
                containers=(),
            )
        )
    return tuple(services)


def parse_zones(payload: Any) -> tuple[Zone, ...]:
    """Parse zones (services with children) of the v2 summary payload."""
    zones: list[Zone] = []
    for item in _services_list(payload):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        children = item.get("children") or []
        if not name or not isinstance(children, list) or not children:
            continue
        services: list[ZoneService] = []
        for entry in children:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            services.append(
                ZoneService(
                    slug=_slugify(str(entry.get("name"))),
                    name=str(entry.get("name")),
                    status=status_from_value(entry.get("current_incident_type")),
                )
            )
        zones.append(
            Zone(
                id=str(item.get("id") or ""),
                slug=_slugify(str(name)),
                name=str(name),
                services=tuple(services),
            )
        )
    return tuple(zones)


def _latest_description(item: dict) -> str:
    """Return the latest update description, falling back to description/title."""
    updates = item.get("updates")
    if isinstance(updates, list):
        for update in reversed(updates):
            if isinstance(update, dict):
                body = update.get("description") or update.get("body")
                if body:
                    return to_plain_text(str(body))
    description = item.get("description")
    if description:
        return to_plain_text(str(description))
    return str(item.get("title") or "")


def parse_notices(payload: Any) -> tuple[list[Notice], list[Notice]]:
    """Split the v2 summary payload into active incidents and maintenances.

    Incidents come from the ``incidents`` array (lifecycle "active");
    maintenances from the ``maintenances`` array (lifecycle "pending").
    Entries without id or title are skipped.
    """
    incidents: list[Notice] = []
    for item in _item_list(payload, "incidents"):
        if not isinstance(item, dict):
            continue
        notice_id = item.get("id")
        title = item.get("title")
        if not notice_id or not title:
            continue
        incidents.append(
            Notice(
                id=str(notice_id),
                notice_type="incident",
                title=str(title),
                status=str(item.get("status") or ""),
                severity=item.get("type"),
                lifecycle="active",
                starts_at=item.get("starts_at"),
                ends_at=item.get("ends_at"),
                description=_latest_description(item),
            )
        )
    maintenances: list[Notice] = []
    for item in _item_list(payload, "maintenances"):
        if not isinstance(item, dict):
            continue
        notice_id = item.get("id")
        title = item.get("title")
        if not notice_id or not title:
            continue
        maintenances.append(
            Notice(
                id=str(notice_id),
                notice_type="maintenance",
                title=str(title),
                status=str(item.get("status") or ""),
                severity=item.get("type"),
                lifecycle="pending",
                starts_at=item.get("starts_at"),
                ends_at=item.get("ends_at"),
                description=_latest_description(item),
            )
        )
    return incidents, maintenances
