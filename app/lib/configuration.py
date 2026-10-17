"""Configuration loading for the LAMETRIC Exoscale status API.

The StatusPal API v2 is public open data: no API key is used.

TOML values arrive typed as ``object``; every value is validated
(``isinstance``) before being stored in the frozen ``AppConfig``.
"""
from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"

#: Legacy aliases accepted in [status-logo], mapped to canonical keys.
ICON_ALIASES: Mapping[str, str] = {
    "minor": "down-minor",
    "major": "down-major",
    "critical": "down-fire",
    "maintenance": "scheduled",
    "unknown": "no-status",
}

REQUIRED_ICONS: tuple[str, ...] = (
    "up",
    "down-minor",
    "down-major",
    "down-fire",
    "scheduled",
    "no-status",
    "tool",
)


class ConfigurationError(Exception):
    """Raised when the configuration is missing or invalid."""


@dataclass(frozen=True)
class AppConfig:
    """Immutable application configuration."""

    statuspal_base_url: str
    status_page_subdomain: str
    request_timeout_seconds: float
    cache_ttl_seconds: float
    app_name: str
    app_logo: str
    status_icons: dict[str, str]
    rate_limit_per_minute: int


def _as_table(raw: Mapping[str, object], name: str) -> dict[str, object]:
    """Return the required [name] table, or raise ConfigurationError."""
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigurationError(f"missing or invalid [{name}] table")
    return value


def _optional_table(raw: Mapping[str, object], name: str) -> dict[str, object]:
    """Return the optional [name] table, or an empty mapping when absent."""
    value = raw.get(name)
    return value if isinstance(value, dict) else {}


def _require_str(table: Mapping[str, object], key: str, where: str) -> str:
    """Return a required non-empty string value, or raise ConfigurationError."""
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{where} must define a non-empty string '{key}'")
    return value


def _require_number(
    table: Mapping[str, object], key: str, default: float, where: str
) -> float:
    """Return a required positive number, using default when the key is absent."""
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{where} '{key}' must be a number")
    number = float(value)
    if number <= 0:
        raise ConfigurationError(f"{where} '{key}' must be positive")
    return number


def _normalize_icons(raw: Mapping[str, object]) -> dict[str, str]:
    """Normalize icon keys (accepting legacy aliases) and check presence."""
    icons: dict[str, str] = {}
    for key, value in raw.items():
        icons[ICON_ALIASES.get(key, key)] = str(value)
    missing = [key for key in REQUIRED_ICONS if key not in icons]
    if missing:
        raise ConfigurationError(
            f"[status-logo] is missing required keys: {', '.join(missing)}"
        )
    return icons


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load the application configuration from a TOML file.

    Raises ConfigurationError when the file is missing or invalid, or when
    a required value (base_url, subdomain, app name/logo, icons) is absent.
    """
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    try:
        with open(config_path, "rb") as handle:
            raw: dict[str, object] = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigurationError(f"config file not found: {config_path}") from exc
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"invalid config file {config_path}: {exc}") from exc

    statuspal = _as_table(raw, "statuspal")
    base_url = _require_str(statuspal, "base_url", "[statuspal]")
    subdomain = _require_str(statuspal, "status_page_subdomain", "[statuspal]")
    timeout = _require_number(
        statuspal, "request_timeout_seconds", 10.0, "[statuspal]"
    )

    lametric_app = _as_table(raw, "lametric-app")
    app_name = _require_str(lametric_app, "name", "[lametric-app]")
    app_logo = _require_str(lametric_app, "logo", "[lametric-app]")

    status_icons = _normalize_icons(_as_table(raw, "status-logo"))

    return AppConfig(
        statuspal_base_url=base_url.rstrip("/"),
        status_page_subdomain=subdomain,
        request_timeout_seconds=timeout,
        cache_ttl_seconds=_require_number(
            _optional_table(raw, "caching"), "ttl_seconds", 30.0, "[caching]"
        ),
        app_name=app_name,
        app_logo=app_logo,
        status_icons=status_icons,
        rate_limit_per_minute=int(
            _require_number(
                _optional_table(raw, "security"),
                "rate_limit_per_minute",
                120.0,
                "[security]",
            )
        ),
    )
