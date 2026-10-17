"""Shared fixtures for the test-suite.

All fixtures are built from realistic payloads that follow the
StatusPal "next" API (v1) OpenAPI specification.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture()
def status_page_payload() -> dict:
    return _fixture("status_page.json")


@pytest.fixture()
def services_payload() -> dict:
    return _fixture("services.json")


@pytest.fixture()
def containers_payload() -> dict:
    return _fixture("containers.json")


@pytest.fixture()
def notices_payload() -> dict:
    return _fixture("notices.json")


@pytest.fixture()
def valid_config_toml(tmp_path: Path) -> Path:
    """Write a valid config.toml and return its path."""
    path = tmp_path / "config.toml"
    path.write_text(
        """
[statuspal]
base_url = "https://next.statuspal.io/api/v1"
status_page_subdomain = "exoscalestatus"
request_timeout_seconds = 10

[caching]
ttl_seconds = 30

[lametric-app]
name = "Exoscale"
logo = "17776"

[status-logo]
up = "120"
minor = "1067"
major = "124"
critical = "2715"
maintenance = "7419"
unknown = "625"
tool = "93"

[lametric-country]
CH = "469"
DE = "512"
AT = "2954"
BG = "20415"
""",
        encoding="utf-8",
    )
    return path
