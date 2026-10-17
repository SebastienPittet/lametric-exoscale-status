"""Build the frames displayed by a LAMETRIC Time clock."""
from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict

from lib.models import Lifecycle, PageStatus, Status, StatusData
from lib.subscription import Subscription

MAX_FRAMES = 15
FRAME_TEXT_LIMIT = 32


class Frame(TypedDict):
    """One LAMETRIC frame: an icon id and a text line."""

    icon: str
    text: str


class FramesPayload(TypedDict):
    """The JSON document sent to a LAMETRIC clock."""

    frames: list[Frame]


_ICON_BY_STATUS: dict[Status, str] = {
    Status.OK: "up",
    Status.MINOR: "down-minor",
    Status.MAJOR: "down-major",
    Status.CRITICAL: "down-fire",
    Status.MAINTENANCE: "scheduled",
    Status.UNKNOWN: "no-status",
}


def _clip(text: str, limit: int = FRAME_TEXT_LIMIT) -> str:
    """Truncate text to limit characters (limit-1 + ellipsis when longer)."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "\u2026"


def _finalize(frames: list[Frame], icons: Mapping[str, str]) -> FramesPayload:
    """Truncate texts and cap the list at MAX_FRAMES with an overflow note."""
    frames = [
        Frame(icon=frame["icon"], text=_clip(frame["text"])) for frame in frames
    ]
    if len(frames) > MAX_FRAMES:
        removed = len(frames) - (MAX_FRAMES - 1)
        frames = frames[: MAX_FRAMES - 1]
        frames.append(
            Frame(icon=icons["no-status"], text=f"+{removed} more\u2026")
        )
    return FramesPayload(frames=frames)


def build_frames(
    data: StatusData,
    app_name: str,
    app_logo: str,
    icons: Mapping[str, str],
    subscription: Subscription,
) -> FramesPayload:
    """Return the frames for the clock, filtered by the subscription."""
    frames = [Frame(icon=app_logo, text=app_name)]

    if data.page_status is PageStatus.UNKNOWN:
        frames.append(Frame(icon=icons["no-status"], text="Status unavailable"))
        return _finalize(frames, icons)

    if subscription.zones:
        zones = [zone for zone in data.zones if zone.slug.lower() in subscription.zones]
        if not zones:
            frames.append(
                Frame(icon=icons["no-status"], text="No subscribed services matched")
            )
            return _finalize(frames, icons)
    else:
        zones = list(data.zones)

    def allowed(slug: str, name: str) -> bool:
        if not subscription.services:
            return True
        return slug in subscription.services or name.lower() in subscription.services

    impacted = False
    for zone in zones:
        for service in zone.services:
            if service.status is Status.OK or not allowed(service.slug, service.name):
                continue
            impacted = True
            frames.append(
                Frame(
                    icon=icons[_ICON_BY_STATUS[service.status]],
                    text=f"{zone.name} {service.name}",
                )
            )

    for global_service in data.services:
        if global_service.status is Status.OK:
            continue
        if not allowed(global_service.slug, global_service.name):
            continue
        impacted = True
        frames.append(
            Frame(
                icon=icons[_ICON_BY_STATUS[global_service.status]],
                text=global_service.name,
            )
        )

    if not impacted:
        if data.page_status is PageStatus.OPERATIONAL:
            frames.append(Frame(icon=icons["up"], text="HEALTHY"))
        else:
            frames.append(
                Frame(
                    icon=icons["no-status"],
                    text=f"Status: {data.page_status.value}",
                )
            )

    for notice in data.maintenances[:3]:
        if notice.lifecycle is Lifecycle.PENDING:
            frames.append(
                Frame(icon=icons["scheduled"], text=f"Maintenance: {notice.title}")
            )
        else:
            frames.append(
                Frame(
                    icon=icons["scheduled"],
                    text=f"Maintenance in progress: {notice.title}",
                )
            )

    return _finalize(frames, icons)
