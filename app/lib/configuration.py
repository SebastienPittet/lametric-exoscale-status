"""Configuration loading for the LAMETRIC Exoscale status API.

The StatusPal API v2 is public: no API key is required. When the optional
STATUSPAL_API_KEY environment variable is set, the key is sent to StatusPal
as a Bearer token; it must never be stored in the configuration file.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"

API_KEY_ENV_VAR = "STATUSPAL_API_KEY"

#: Legacy aliases accepted in [status-logo], mapped to canonical keys.
ICON_ALIASES = {
    "minor": "down-minor",
    "major": "down-major",
    "critical": "down-fire",
    "maintenance": "scheduled",
    "unknown": "no-status",
}

REQUIRED_ICONS = (
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
    statuspal_api_key: str
    request_timeout_seconds: float
    cache_ttl_seconds: float
    app_name: str
    app_logo: str
    status_icons: dict[str, str]
    rate_limit_per_minute: int


def _normalize_icons(raw: dict) -> dict[str, str]:
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
    The StatusPal API key is optional: it defaults to "" when the
    STATUSPAL_API_KEY environment variable is not set.
    """
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    try:
        with open(config_path, "rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigurationError(f"config file not found: {config_path}") from exc
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(f"invalid config file {config_path}: {exc}") from exc

    statuspal = raw.get("statuspal") or {}
    base_url = statuspal.get("base_url")
    subdomain = statuspal.get("status_page_subdomain")
    if not base_url or not subdomain:
        raise ConfigurationError(
            "[statuspal] must define base_url and status_page_subdomain"
        )

    lametric_app = raw.get("lametric-app") or {}
    app_name = lametric_app.get("name")
    app_logo = lametric_app.get("logo")
    if not app_name or not app_logo:
        raise ConfigurationError("[lametric-app] must define name and logo")

    status_icons = _normalize_icons(raw.get("status-logo") or {})

    # The public API v2 works without a key; only use it when configured.
    api_key = os.environ.get(API_KEY_ENV_VAR, "").strip()

    return AppConfig(
        statuspal_base_url=str(base_url).rstrip("/"),
        status_page_subdomain=str(subdomain),
        statuspal_api_key=api_key,
        request_timeout_seconds=float(statuspal.get("request_timeout_seconds", 10)),
        cache_ttl_seconds=float((raw.get("caching") or {}).get("ttl_seconds", 30)),
        app_name=str(app_name),
        app_logo=str(app_logo),
        status_icons=status_icons,
        rate_limit_per_minute=int(
            (raw.get("security") or {}).get("rate_limit_per_minute", 120)
        ),
    )
