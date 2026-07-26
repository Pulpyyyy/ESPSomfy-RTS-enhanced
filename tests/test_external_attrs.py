"""Tests for the external-attrs contract on ESPSomfyShade.

The property-level tests build a shade on a stubbed controller (as in
test_websocket_events.py) and drive its hass.data by hand. The end-to-end test
sets up a real config entry (as in test_setup.py) and checks the shade
registers as a reader, carries injected extras through its own property, and
unregisters on unload.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.espsomfy_rts_enhanced.const import DOMAIN
from custom_components.espsomfy_rts_enhanced.cover import (
    EXTERNAL_ATTRS_DATA,
    EXTERNAL_ATTRS_SIGNAL,
    ESPSomfyShade,
    _external_attrs_store,
)

from .conftest import (
    API_URL,
    DISCOVERY_PAYLOAD,
    DISCOVERY_URL,
    HOST,
    LOGIN_URL,
    SERVER_ID,
)

SHADES_URL = f"{API_URL}/shades"
GROUPS_URL = f"{API_URL}/groups"

SHADES = [
    {
        "shadeId": 1, "type": 4, "shadeType": 4, "name": "Living Room",
        "remoteAddress": 100001, "direction": 0, "position": 0, "target": 0,
        "myPos": 30, "tiltType": 0, "tiltPosition": 100, "tiltDirection": 0,
        "flipCommands": False, "flipPosition": False, "paired": True,
        "bitLength": 56, "proto": 0, "flags": 0,
    },
]


def _shade(**overrides: Any) -> ESPSomfyShade:
    """Build a shade entity on a stubbed controller (no hass wired)."""
    controller = MagicMock()
    controller.unique_id = "espsomfy_1a2b3c4d"
    data = {
        "shadeId": 3,
        "name": "Living room",
        "position": 40,
        "shadeType": 1,
        "tiltType": 0,
    } | overrides
    return ESPSomfyShade(controller, data)


# ── _external_attrs_store ─────────────────────────────────────────────────────

def test_external_store_creates_and_is_idempotent() -> None:
    hass = SimpleNamespace(data={})
    store = _external_attrs_store(hass)
    assert store == {"readers": set(), "injected": {}}
    store["readers"].add("cover.x")
    store["injected"]["cover.x"] = {"facade": "south"}
    # Second call returns the SAME store, never resets it.
    store2 = _external_attrs_store(hass)
    assert store2 is store
    assert store2["readers"] == {"cover.x"}
    assert store2["injected"] == {"cover.x": {"facade": "south"}}


# ── extra_state_attributes (soft merge) ───────────────────────────────────────

def test_extra_state_attributes_merges_injected() -> None:
    shade = _shade()
    shade.entity_id = "cover.living"
    shade._state_attributes = {"my_pos": 30}
    shade.hass = SimpleNamespace(
        data={
            EXTERNAL_ATTRS_DATA: {
                "readers": {"cover.living"},
                "injected": {"cover.living": {"facade": "south", "memory": 42}},
            }
        }
    )
    assert shade.extra_state_attributes == {
        "my_pos": 30,
        "facade": "south",
        "memory": 42,
    }


def test_extra_state_attributes_without_contract_returns_own() -> None:
    shade = _shade()
    shade.entity_id = "cover.living"
    shade._state_attributes = {"my_pos": 30}
    shade.hass = SimpleNamespace(data={})
    # No contract key → the shade is autonomous, only its own attributes.
    assert shade.extra_state_attributes is shade._state_attributes


def test_extra_state_attributes_no_injected_entry_returns_own() -> None:
    shade = _shade()
    shade.entity_id = "cover.living"
    shade._state_attributes = {"my_pos": 30}
    shade.hass = SimpleNamespace(
        data={EXTERNAL_ATTRS_DATA: {"readers": {"cover.living"}, "injected": {}}}
    )
    assert shade.extra_state_attributes is shade._state_attributes


def test_extra_state_attributes_no_hass_returns_own() -> None:
    shade = _shade()
    shade._state_attributes = {"a": 1}
    shade.hass = None
    assert shade.extra_state_attributes is shade._state_attributes


# ── dispatcher callback ───────────────────────────────────────────────────────

def test_dispatcher_callback_writes_only_for_matching_entity() -> None:
    shade = _shade()
    shade.entity_id = "cover.living"
    with patch.object(ESPSomfyShade, "async_write_ha_state") as write:
        shade._external_attrs_updated("cover.other")
        assert write.call_count == 0
        shade._external_attrs_updated("cover.living")
        assert write.call_count == 1


def test_cleanup_removes_entity_from_contract() -> None:
    shade = _shade()
    shade.entity_id = "cover.living"
    shade.hass = SimpleNamespace(
        data={
            EXTERNAL_ATTRS_DATA: {
                "readers": {"cover.living", "cover.other"},
                "injected": {"cover.living": {"facade": "south"}},
            }
        }
    )
    shade._external_attrs_cleanup()
    store = shade.hass.data[EXTERNAL_ATTRS_DATA]
    assert store["readers"] == {"cover.other"}
    assert store["injected"] == {}


# ── end-to-end against a real config entry ────────────────────────────────────

async def test_shade_registers_as_reader_and_carries_injected(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """A set-up shade joins "readers", carries injected extras, and leaves on unload."""
    aioclient_mock.get(DISCOVERY_URL, json=DISCOVERY_PAYLOAD)
    aioclient_mock.put(LOGIN_URL, json={"success": True, "apiKey": "0123456789"})
    aioclient_mock.get(SHADES_URL, json=SHADES)
    aioclient_mock.get(GROUPS_URL, json=[])

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: HOST, CONF_PIN: "1234"},
        unique_id=f"espsomfy_{SERVER_ID}",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.espsomfy_rts_enhanced.controller.ESPSomfyController.ws_connect",
        return_value=None,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    covers = hass.states.async_entity_ids("cover")
    assert covers, "expected at least one cover entity"
    store = hass.data[EXTERNAL_ATTRS_DATA]
    assert set(covers) <= store["readers"]

    entity_id = covers[0]
    # Deposit extras and notify — the entity must merge them into its state.
    store["injected"][entity_id] = {"facade": "south", "memory": 42}
    async_dispatcher_send(hass, EXTERNAL_ATTRS_SIGNAL, entity_id)
    await hass.async_block_till_done()
    attrs = hass.states.get(entity_id).attributes
    assert attrs.get("facade") == "south"
    assert attrs.get("memory") == 42

    # Unload → the shade drops itself from readers and injected.
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    store = hass.data[EXTERNAL_ATTRS_DATA]
    assert entity_id not in store["readers"]
    assert entity_id not in store["injected"]
