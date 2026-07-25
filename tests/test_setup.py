"""Regression tests for config-entry setup creating the cover entities.

These guard the bug where async_setup_entry stopped loading the shade and group
lists: get_initial() only fetches /discovery, which a firmware in full-auth mode
returns without the shade/group arrays, so every cover came back unavailable.
"""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PIN
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.espsomfy_rts_enhanced.const import DOMAIN

from .conftest import API_URL, DISCOVERY_PAYLOAD, DISCOVERY_URL, HOST, LOGIN_URL, SERVER_ID

SHADES_URL = f"{API_URL}/shades"
GROUPS_URL = f"{API_URL}/groups"

# Two ordinary roller shades, as /shades returns them. /discovery in full-auth
# mode carries none of this (DISCOVERY_PAYLOAD has empty arrays), so the entities
# can only exist if setup explicitly loads /shades after logging in.
SHADES = [
    {
        "shadeId": 1, "type": 4, "shadeType": 4, "name": "Living Room",
        "remoteAddress": 100001, "direction": 0, "position": 0, "target": 0,
        "myPos": 30, "tiltType": 0, "tiltPosition": 100, "tiltDirection": 0,
        "flipCommands": False, "flipPosition": False, "paired": True,
        "bitLength": 56, "proto": 0, "flags": 0,
    },
    {
        "shadeId": 2, "type": 4, "shadeType": 4, "name": "Kitchen",
        "remoteAddress": 100002, "direction": 0, "position": 100, "target": 100,
        "myPos": 30, "tiltType": 0, "tiltPosition": 100, "tiltDirection": 0,
        "flipCommands": False, "flipPosition": False, "paired": True,
        "bitLength": 56, "proto": 0, "flags": 0,
    },
]


async def test_setup_loads_shades_and_creates_covers(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """A full-auth device (no shades in /discovery) must still get its covers."""
    aioclient_mock.get(DISCOVERY_URL, json=DISCOVERY_PAYLOAD)  # no shades/groups
    aioclient_mock.put(LOGIN_URL, json={"success": True, "apiKey": "0123456789"})
    aioclient_mock.get(SHADES_URL, json=SHADES)
    aioclient_mock.get(GROUPS_URL, json=[])

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: HOST, CONF_PIN: "1234"},
        unique_id=f"espsomfy_{SERVER_ID}",
    )
    entry.add_to_hass(hass)

    # Don't open a real websocket during the test.
    with patch(
        "custom_components.espsomfy_rts_enhanced.controller.ESPSomfyController.ws_connect",
        return_value=None,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    controller = entry.runtime_data
    # Root cause: the shade list must be populated (was [] before the fix).
    assert len(controller.api.shades) == len(SHADES)
    # End result: one cover entity per shade (was zero before the fix).
    covers = hass.states.async_entity_ids("cover")
    assert len(covers) == len(SHADES)
