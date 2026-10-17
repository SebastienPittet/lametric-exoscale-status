"""Tests for lib.configuration (TDD)."""
from pathlib import Path

import pytest
from lib.configuration import ConfigurationError, load_config

FULL_TOML = """
[statuspal]
base_url = "https://statuspal.eu/api/v2"
status_page_subdomain = "exoscalestatus"
request_timeout_seconds = 10

[caching]
ttl_seconds = 30

[lametric-app]
name = "Exoscale"
logo = "17776"

[status-logo]
up = "120"
down-minor = "1067"
down-major = "124"
down-fire = "2715"
scheduled = "7419"
no-status = "625"
tool = "93"
"""


def write(tmp_path: Path, drop_key: str | None = None) -> Path:
    lines = [
        line
        for line in FULL_TOML.splitlines()
        if not (drop_key and line.strip().startswith(drop_key + " ="))
    ]
    p = tmp_path / "config.toml"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def test_loads_valid_config(valid_config_toml: Path) -> None:
    cfg = load_config(valid_config_toml)
    assert cfg.statuspal_base_url == "https://statuspal.eu/api/v2"
    assert cfg.status_page_subdomain == "exoscalestatus"
    assert cfg.app_name == "Exoscale"
    assert cfg.app_logo == "17776"
    assert cfg.status_icons["up"] == "120"
    assert cfg.request_timeout_seconds == 10
    assert cfg.cache_ttl_seconds == 30


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        load_config(tmp_path / "nope.toml")


def test_invalid_toml_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.toml"
    p.write_text("[statuspal\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_config(p)


def test_invalid_number_raises(tmp_path: Path) -> None:
    p = write(tmp_path)
    p.write_text(
        p.read_text(encoding="utf-8").replace(
            "request_timeout_seconds = 10",
            "request_timeout_seconds = \"ten\"",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError):
        load_config(p)


@pytest.mark.parametrize(
    "drop", ["base_url", "status_page_subdomain", "name", "logo", "up", "tool"]
)
def test_missing_required_key_raises(tmp_path: Path, drop: str) -> None:
    with pytest.raises(ConfigurationError):
        load_config(write(tmp_path, drop))


def test_defaults_when_optional_missing(tmp_path: Path) -> None:
    lines = [
        line
        for line in FULL_TOML.splitlines()
        if "request_timeout_seconds" not in line
        and "ttl_seconds" not in line
        and "[caching]" not in line
    ]
    p = tmp_path / "config.toml"
    p.write_text("\n".join(lines), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.request_timeout_seconds == 10.0
    assert cfg.cache_ttl_seconds == 30.0
    assert cfg.rate_limit_per_minute == 120
