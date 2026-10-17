"""Parsing of the LAMETRIC subscription query parameters (zones/services)."""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_TOKENS_PER_PARAM = 20
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")


class SubscriptionError(Exception):
    """Raised when a subscription parameter value is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class Subscription:
    """A set of zones and/or services to display on the clock."""

    zones: frozenset[str] = frozenset()
    services: frozenset[str] = frozenset()

    @property
    def empty(self) -> bool:
        """True when neither zones nor services are subscribed."""
        return not self.zones and not self.services


def _parse_tokens(raw: object, param: str) -> frozenset[str]:
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        items = raw.split(",")
    elif isinstance(raw, (list, tuple)):
        items = [str(item) for item in raw]
    else:
        items = [str(raw)]
    tokens: set[str] = set()
    for item in items:
        token = str(item).strip().lower()
        if not token:
            continue
        if not _TOKEN_RE.match(token):
            raise SubscriptionError(
                f"invalid value for parameter '{param}': {token!r}"
            )
        tokens.add(token)
    if len(tokens) > MAX_TOKENS_PER_PARAM:
        raise SubscriptionError(
            f"too many values for parameter '{param}' "
            f"(max {MAX_TOKENS_PER_PARAM})"
        )
    return frozenset(tokens)


def parse_subscription(args: dict) -> Subscription:
    """Parse the 'zones' and 'services' request parameters into a Subscription."""
    return Subscription(
        zones=_parse_tokens(args.get("zones"), "zones"),
        services=_parse_tokens(args.get("services"), "services"),
    )
