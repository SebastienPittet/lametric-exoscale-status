"""Build the frames displayed by a LAMETRIC Time clock."""
from __future__ import annotations

from lib.models import Status, StatusData
from lib.subscription import Subscription

MAX_FRAMES = 15
FRAME_TEXT_LIMIT = 32

_ICON_BY_STATUS = {
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


def _finalize(frames: list[dict], icons: dict) -> dict:
    """Truncate texts and cap the list at MAX_FRAMES with an overflow note."""
    frames = [
        {"icon": frame["icon"], "text": _clip(frame["text"])} for frame in frames
    ]
    if len(frames) > MAX_FRAMES:
        removed = len(frames) - (MAX_FRAMES - 1)
        frames = frames[: MAX_FRAMES - 1]
        frames.append(
            {"icon": icons["no-status"], "text": f"+{removed} more\u2026"}
        )
    return {"frames": frames}


def build_frames(
    data: StatusData,
    app_name: str,
    app_logo: str,
    icons: dict,
    subscription: Subscription,
) -> dict:
    """Return {"frames": [{"icon": ..., "text": ...}, ...]} for the clock."""
    frames = [{"icon": app_logo, "text": app_name}]

    if data.page_status == "unknown":
        frames.append({"icon": icons["no-status"], "text": "Status unavailable"})
        return _finalize(frames, icons)

    if subscription.zones:
        zones = [zone for zone in data.zones if zone.slug.lower() in subscription.zones]
        if not zones:
            frames.append(
                {"icon": icons["no-status"], "text": "No subscribed services matched"}
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
            if service.status == Status.OK or not allowed(service.slug, service.name):
                continue
            impacted = True
            frames.append(
                {
                    "icon": icons[_ICON_BY_STATUS[service.status]],
                    "text": f"{zone.name} {service.name}",
                }
            )

    for service in data.services:
        if service.scope != "global" or service.status == Status.OK:
            continue
        if not allowed(service.slug, service.name):
            continue
        impacted = True
        frames.append(
            {"icon": icons[_ICON_BY_STATUS[service.status]], "text": service.name}
        )

    if not impacted:
        if data.page_status == "operational":
            frames.append({"icon": icons["up"], "text": "HEALTHY"})
        else:
            frames.append(
                {"icon": icons["no-status"], "text": f"Status: {data.page_status}"}
            )

    for notice in data.maintenances[:3]:
        if notice.lifecycle == "pending":
            frames.append(
                {"icon": icons["scheduled"], "text": f"Maintenance: {notice.title}"}
            )
        else:
            frames.append(
                {
                    "icon": icons["scheduled"],
                    "text": f"Maintenance in progress: {notice.title}",
                }
            )

    return _finalize(frames, icons)
