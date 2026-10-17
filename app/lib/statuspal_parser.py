"""Parsers that turn the public StatusPal API v2 summary payload into domain models.

The v2 summary (``/api/v2/status_pages/{subdomain}/summary``) is a single
public JSON document:

- ``services``: top-level entries; entries with ``children`` are zones
  (each child is a zone service), entries without children are global
  services;
- ``status_page``: page metadata, including ``current_incident_type``;
- ``incidents`` / ``maintenances``: active incidents and maintenances.

The JSON boundary is typed as ``object`` (never ``Any``): every value is
explicitly narrowed with ``isinstance`` before use, so malformed payloads
are tolerated without leaking untyped data into the domain.
"""
from __future__ import annotations

import re

from lib.models import (
    Lifecycle,
    Notice,
    NoticeStatus,
    NoticeType,
    PageStatus,
    Service,
    Status,
    Zone,
    ZoneService,
)

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

#: Mapping of StatusPal v2 incident types to a service Status.
_INCIDENT_TYPE_TO_STATUS: dict[str, Status] = {
    "none": Status.OK,
    "ok": Status.OK,
    "operational": Status.OK,
    "minor": Status.MINOR,
    "major": Status.MAJOR,
    "critical": Status.CRITICAL,
    "maintenance": Status.MAINTENANCE,
    "scheduled": Status.MAINTENANCE,
}

#: Mapping of StatusPal v2 incident types to the page status.
_INCIDENT_TYPE_TO_PAGE_STATUS: dict[str, PageStatus] = {
    "none": PageStatus.OPERATIONAL,
    "ok": PageStatus.OPERATIONAL,
    "operational": PageStatus.OPERATIONAL,
    "minor": PageStatus.DEGRADED,
    "major": PageStatus.UNAVAILABLE,
    "critical": PageStatus.UNAVAILABLE,
    "maintenance": PageStatus.OPERATIONAL,
    "scheduled": PageStatus.OPERATIONAL,
}


def to_plain_text(html: str | None) -> str:
    """Strip HTML tags and collapse whitespace into a single-line text."""
    if html is None:
        return ""
    text = _TAG_RE.sub(" ", str(html))
    return _WHITESPACE_RE.sub(" ", text).strip()


def status_from_value(value: object) -> Status:
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


def page_status_from_value(value: object) -> PageStatus:
    """Map a raw StatusPal v2 incident type to the page status.

    ``None``/empty/"none" mean "no incident" -> OPERATIONAL; minor ->
    DEGRADED; major/critical -> UNAVAILABLE; maintenance/scheduled ->
    OPERATIONAL (a page under maintenance is still a healthy page);
    unknown values -> UNKNOWN.
    """
    if value is None:
        return PageStatus.OPERATIONAL
    key = str(value).strip().lower()
    if key in ("", "none"):
        return PageStatus.OPERATIONAL
    return _INCIDENT_TYPE_TO_PAGE_STATUS.get(key, PageStatus.UNKNOWN)


def notice_status_from_value(value: object) -> NoticeStatus:
    """Map a raw StatusPal v2 notice status to a NoticeStatus.

    Unknown or missing values map to ``NoticeStatus.UNKNOWN``.
    """
    if value is None:
        return NoticeStatus.UNKNOWN
    key = str(value).strip().lower()
    try:
        return NoticeStatus(key)
    except ValueError:
        return NoticeStatus.UNKNOWN


def _slugify(name: str) -> str:
    """Derive a slug from a display name (lowercase, ``-`` separators)."""
    slug = _WHITESPACE_RE.sub("-", name.strip().lower())
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    return slug.strip("-")


def _as_dict(value: object) -> dict[str, object] | None:
    """Narrow a JSON value to an object, or None when it is not one."""
    return value if isinstance(value, dict) else None


def _as_list(value: object) -> list[object] | None:
    """Narrow a JSON value to an array, or None when it is not one."""
    return value if isinstance(value, list) else None


def _as_str(value: object) -> str:
    """Coerce a JSON value to a string (empty string for None)."""
    return "" if value is None else str(value)


def _as_optional_str(value: object) -> str | None:
    """Return the value when it is a non-empty-or-empty string, else None."""
    return value if isinstance(value, str) else None


def _services_list(payload: object) -> list[object]:
    """Return payload["services"] when it is a list, else an empty list."""
    entry = _as_dict(payload)
    if entry is None:
        return []
    return _as_list(entry.get("services")) or []


def _item_list(payload: object, key: str) -> list[object]:
    """Return payload[key] when it is a list, else an empty list."""
    entry = _as_dict(payload)
    if entry is None:
        return []
    return _as_list(entry.get(key)) or []


def parse_status_page(payload: object) -> PageStatus:
    """Return the page status derived from the v2 summary payload.

    ``PageStatus.UNKNOWN`` is returned when no ``status_page`` block can be
    found in the payload.
    """
    entry = _as_dict(payload)
    if entry is None:
        return PageStatus.UNKNOWN
    page = _as_dict(entry.get("status_page"))
    if page is None:
        return PageStatus.UNKNOWN
    return page_status_from_value(page.get("current_incident_type"))


def parse_services(payload: object) -> tuple[Service, ...]:
    """Parse the global (children-less) services of the v2 summary payload."""
    services: list[Service] = []
    for item in _services_list(payload):
        entry = _as_dict(item)
        if entry is None:
            continue
        name = _as_optional_str(entry.get("name"))
        if name is None or _as_list(entry.get("children")):
            continue
        services.append(
            Service(
                id=_as_str(entry.get("id")),
                slug=_slugify(name),
                name=name,
                status=status_from_value(entry.get("current_incident_type")),
            )
        )
    return tuple(services)


def parse_zones(payload: object) -> tuple[Zone, ...]:
    """Parse zones (services with children) of the v2 summary payload."""
    zones: list[Zone] = []
    for item in _services_list(payload):
        entry = _as_dict(item)
        if entry is None:
            continue
        name = _as_optional_str(entry.get("name"))
        children = _as_list(entry.get("children"))
        if name is None or not children:
            continue
        services: list[ZoneService] = []
        for child in children:
            child_entry = _as_dict(child)
            if child_entry is None:
                continue
            child_name = _as_optional_str(child_entry.get("name"))
            if child_name is None:
                continue
            services.append(
                ZoneService(
                    slug=_slugify(child_name),
                    name=child_name,
                    status=status_from_value(child_entry.get("current_incident_type")),
                )
            )
        zones.append(
            Zone(
                id=_as_str(entry.get("id")),
                slug=_slugify(name),
                name=name,
                services=tuple(services),
            )
        )
    return tuple(zones)


def _latest_description(item: dict[str, object]) -> str:
    """Return the latest update description, falling back to description/title."""
    updates = _as_list(item.get("updates"))
    if updates is not None:
        for update in reversed(updates):
            update_entry = _as_dict(update)
            if update_entry is None:
                continue
            body = _as_optional_str(update_entry.get("description")) or (
                _as_optional_str(update_entry.get("body"))
            )
            if body is not None:
                return to_plain_text(body)
    description = _as_optional_str(item.get("description"))
    if description is not None:
        return to_plain_text(description)
    return _as_str(item.get("title"))


def _parse_items(
    payload: object,
    key: str,
    notice_type: NoticeType,
    lifecycle: Lifecycle,
) -> tuple[Notice, ...]:
    """Parse one notice array of the payload, skipping unusable entries."""
    notices: list[Notice] = []
    for item in _item_list(payload, key):
        entry = _as_dict(item)
        if entry is None:
            continue
        notice_id = _as_str(entry.get("id"))
        title = _as_optional_str(entry.get("title"))
        if not notice_id or title is None:
            continue
        notices.append(
            Notice(
                id=notice_id,
                notice_type=notice_type,
                title=title,
                status=notice_status_from_value(entry.get("status")),
                severity=_as_optional_str(entry.get("type")),
                lifecycle=lifecycle,
                starts_at=_as_optional_str(entry.get("starts_at")),
                ends_at=_as_optional_str(entry.get("ends_at")),
                description=_latest_description(entry),
            )
        )
    return tuple(notices)


def parse_notices(
    payload: object,
) -> tuple[tuple[Notice, ...], tuple[Notice, ...]]:
    """Split the v2 summary payload into active incidents and maintenances.

    Incidents come from the ``incidents`` array (lifecycle ACTIVE);
    maintenances from the ``maintenances`` array (lifecycle PENDING).
    Entries without a usable id or title are skipped.
    """
    return (
        _parse_items(payload, "incidents", NoticeType.INCIDENT, Lifecycle.ACTIVE),
        _parse_items(payload, "maintenances", NoticeType.MAINTENANCE, Lifecycle.PENDING),
    )
