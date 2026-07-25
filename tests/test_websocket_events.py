"""Tests for the websocket framing and the state it feeds to the entities."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from homeassistant.components.cover import CoverEntityFeature

from custom_components.espsomfy_rts_enhanced.const import (
    EVT_GROUPSTATE,
    EVT_SHADESTATE,
)
from custom_components.espsomfy_rts_enhanced.controller import SocketListener
from custom_components.espsomfy_rts_enhanced.cover import (
    ESPSomfyShade,
    _linked_shade_ids,
)


def _listener(packets: list[dict[str, Any]]) -> SocketListener:
    """Build a listener that collects the packets it decodes."""
    listener = SocketListener(
        hass=MagicMock(),
        url="ws://192.168.1.10:8080",
        onpacket=packets.append,
        onopen=MagicMock(),
        onclose=MagicMock(),
        onerror=MagicMock(),
    )
    listener.set_filter([EVT_SHADESTATE, EVT_GROUPSTATE])
    return listener


def _shade(**overrides: Any) -> ESPSomfyShade:
    """Build a shade entity on a stubbed controller."""
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


def test_shade_state_writes_state_once() -> None:
    """A shadeState with a position change must write state exactly once.

    A second, unconditional async_write_ha_state() used to run for every event,
    doubling each position step into two state_changed events -- and with an
    attribute-injecting helper (cover_extender) each write dropped then re-added the
    injected attributes, fanning one step out to four events. Only _handle_state_update
    should write for a shade state, and only when something changed.
    """
    shade = _shade(position=40)
    shade.hass = MagicMock()
    shade._controller.data = {
        "shadeId": 3,
        "position": 50,
        "direction": 0,
        "event": EVT_SHADESTATE,
    }
    with patch.object(
        ESPSomfyShade, "enabled", new_callable=PropertyMock, return_value=True
    ), patch.object(ESPSomfyShade, "async_write_ha_state") as write:
        shade._handle_coordinator_update()
    assert write.call_count == 1


def test_shade_state_with_no_change_writes_nothing() -> None:
    """A shadeState that changes nothing must not write state at all."""
    shade = _shade(position=40)
    shade.hass = MagicMock()
    shade._controller.data = {"shadeId": 3, "position": 40, "event": EVT_SHADESTATE}
    with patch.object(
        ESPSomfyShade, "enabled", new_callable=PropertyMock, return_value=True
    ), patch.object(ESPSomfyShade, "async_write_ha_state") as write:
        shade._handle_coordinator_update()
    assert write.call_count == 0


def test_shade_state_is_decoded() -> None:
    """A shadeState frame is decoded and tagged with its event name."""
    packets: list[dict[str, Any]] = []
    _listener(packets)._process_message(
        '42[shadeState,{"shadeId":3,"position":50,"direction":0}]'
    )

    assert packets == [
        {"shadeId": 3, "position": 50, "direction": 0, "event": EVT_SHADESTATE}
    ]


def test_group_state_carries_bare_shade_ids() -> None:
    """groupState names the linkage 'shades' and lists ids, not objects."""
    packets: list[dict[str, Any]] = []
    _listener(packets)._process_message(
        '42[groupState,{"groupId":1,"name":"All","shades":[3,4,7],"flags":0}]'
    )

    assert len(packets) == 1
    assert _linked_shade_ids(packets[0]) == [3, 4, 7]


def test_linked_shade_ids_accepts_both_spellings() -> None:
    """The REST spelling and the websocket spelling yield the same ids."""
    rest = {"linkedShades": [{"shadeId": 3, "shadeType": 1}, {"shadeId": 4}]}
    socket = {"shades": [3, 4]}

    assert _linked_shade_ids(rest) == [3, 4]
    assert _linked_shade_ids(socket) == [3, 4]
    # No linkage at all is not the same as an empty group.
    assert _linked_shade_ids({"groupId": 1}) is None
    assert _linked_shade_ids({"groupId": 1, "shades": []}) == []


@pytest.mark.parametrize(
    "message",
    [
        '42[shadeState,[1,2,3]]',
        '42[shadeState,"offline"]',
        '42[shadeState,null]',
        '42[shadeState,{"shadeId":3]',
    ],
    ids=["array", "string", "null", "malformed"],
)
def test_payloads_that_are_not_objects_are_ignored(message: str) -> None:
    """A frame the integration cannot route is dropped, not raised."""
    packets: list[dict[str, Any]] = []
    _listener(packets)._process_message(message)

    assert packets == []


def test_filtered_events_are_dropped() -> None:
    """An event outside of the subscribed filter never reaches the coordinator."""
    packets: list[dict[str, Any]] = []
    _listener(packets)._process_message('42[memStatus,{"free":1000}]')

    assert packets == []


def test_unknown_position_sentinel_is_not_stored() -> None:
    """The firmware sends -1 for an unknown position, which is not a position."""
    shade = _shade(position=40)
    assert shade.current_cover_position == 60

    with patch.object(ESPSomfyShade, "async_write_ha_state"):
        shade._handle_state_update({"position": -1})
        assert shade.current_cover_position == 60

        shade._handle_state_update({"position": 100})
        assert shade.current_cover_position == 0

        shade._handle_state_update({"position": 0})
        assert shade.current_cover_position == 100


def test_unknown_tilt_sentinel_is_not_stored() -> None:
    """The same sentinel applies to the tilt position of a tilting shade."""
    shade = _shade(tiltType=1, tiltPosition=30)
    assert shade.current_cover_tilt_position == 70

    with patch.object(ESPSomfyShade, "async_write_ha_state"):
        shade._handle_state_update({"tiltPosition": -1})
        assert shade.current_cover_tilt_position == 70


def test_garage_door_offers_its_commands_before_any_state_event() -> None:
    """A door that never moved still opens, closes and stops."""
    shade = _shade(shadeType=5, position=100)

    assert shade.supported_features & CoverEntityFeature.OPEN
    assert shade.supported_features & CoverEntityFeature.CLOSE


def test_euromode_tilt_is_supported() -> None:
    """tiltType 4 is a tilting motor like 1 and 2."""
    shade = _shade(tiltType=4, tiltPosition=0)

    assert shade.supported_features & CoverEntityFeature.SET_TILT_POSITION

    with patch.object(ESPSomfyShade, "async_write_ha_state"):
        shade._handle_state_update({"tiltType": 4, "tiltPosition": 25})

    assert shade.current_cover_tilt_position == 75
