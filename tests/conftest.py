"""Fixtures shared by the ESPSomfy-RTS Enhanced tests."""

from __future__ import annotations

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

HOST = "192.168.1.10"
SERVER_ID = "1a2b3c4d"
API_URL = f"http://{HOST}:8081"
DISCOVERY_URL = f"{API_URL}/discovery"
LOGIN_URL = f"{API_URL}/login"

# Trimmed down /discovery answer of a device running the current firmware.
DISCOVERY_PAYLOAD = {
    "serverId": SERVER_ID,
    "version": "3.1.0",
    "latest": "3.1.0",
    "model": "ESPSomfyRTS",
    "hostname": "ESPSomfyRTS",
    "authType": 0,
    "permissions": 1,
    "chipModel": "S3",
    "connType": "Wifi",
    "checkForUpdate": True,
    "memory": {"max": 100000, "free": 90000, "min": 80000, "total": 300000},
    "rooms": [],
    "shades": [],
    "groups": [],
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components in every test."""
    return
