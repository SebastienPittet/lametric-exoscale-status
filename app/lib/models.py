"""Domain models for the Exoscale / StatusPal status data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable, Protocol


class Status(str, Enum):
    """Status of a service, as reported by StatusPal."""

    OK = "ok"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"
    MAINTENANCE = "maintenance"
    UNKNOWN = "unknown"


class PageStatus(str, Enum):
    """Overall status of the status page."""

    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class NoticeType(str, Enum):
    """Kind of a notice."""

    INCIDENT = "incident"
    MAINTENANCE = "maintenance"


class Lifecycle(str, Enum):
    """Lifecycle state of a notice."""

    PENDING = "pending"
    ACTIVE = "active"


_SEVERITY_RANK: dict[Status, int] = {
    Status.OK: 0,
    Status.MAINTENANCE: 1,
    Status.MINOR: 2,
    Status.MAJOR: 3,
    Status.CRITICAL: 4,
    Status.UNKNOWN: 0,  # unknown is treated like OK
}


def worst(statuses: Iterable[Status]) -> Status:
    """Return the most severe status of the iterable (OK when empty)."""
    result = Status.OK
    for status in statuses:
        if _SEVERITY_RANK.get(status, 0) > _SEVERITY_RANK[result]:
            result = status
    return result


class StatusDataProvider(Protocol):
    """Anything that can fetch a status snapshot (the client, or a test double)."""

    def fetch_status_data(self) -> StatusData: ...


@dataclass(frozen=True)
class Service:
    """A service of the status page (global or per-container scope)."""

    id: str
    slug: str
    name: str
    status: Status
    scope: str
    containers: tuple[str, ...]


@dataclass(frozen=True)
class ZoneService:
    """A service entry inside a zone (container)."""

    slug: str
    name: str
    status: Status


@dataclass(frozen=True)
class Zone:
    """A zone (container) and the services available in it."""

    id: str
    slug: str
    name: str
    services: tuple[ZoneService, ...]

    @property
    def worst_status(self) -> Status:
        """Most severe status among the zone services (OK when empty)."""
        return worst([service.status for service in self.services])


@dataclass(frozen=True)
class Notice:
    """An incident or maintenance notice."""

    id: str
    notice_type: NoticeType
    title: str
    status: str
    severity: str | None
    lifecycle: Lifecycle
    starts_at: str | None
    ends_at: str | None
    description: str


@dataclass(frozen=True)
class StatusData:
    """Aggregated status snapshot for one fetch of the StatusPal API."""

    page_status: PageStatus
    services: tuple[Service, ...]
    zones: tuple[Zone, ...]
    incidents: tuple[Notice, ...]
    maintenances: tuple[Notice, ...]
    fetched_at: datetime | None
    errors: tuple[str, ...]
