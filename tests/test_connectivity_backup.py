"""Tests for the connectivity sensor, the backup failures and the retention."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import timedelta
import logging
import os
from pathlib import Path
import stat
import sys
from typing import Any
from unittest.mock import patch

import pytest

from homeassistant.const import CONF_HOST, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.espsomfy_rts_enhanced.const import (
    CONF_MAX_BACKUPS,
    DEFAULT_MAX_BACKUPS,
    DOMAIN,
)
from custom_components.espsomfy_rts_enhanced.controller import (
    PROBE_INTERVAL,
    ESPSomfyAPI,
    ESPSomfyController,
)

from .conftest import DISCOVERY_PAYLOAD, HOST, SERVER_ID

OTHER_HOST = "192.168.1.11"
OTHER_SERVER_ID = "5e6f7a8b"
BACKUP_PAYLOAD = b'{"version": 1, "shades": []}'

# The longest the sensor may take to follow the device, acceptance criterion.
DETECTION_BUDGET = timedelta(seconds=90)

# The autouse fixture replaces probe(), kept here to test the real one.
REAL_PROBE = ESPSomfyAPI.probe


@pytest.fixture
def probe_results() -> dict[str, bool]:
    """Outcome of the mocked HTTP probe, per host (True when absent)."""
    return {}


@pytest.fixture
def probe_calls() -> list[str]:
    """Hosts the mocked HTTP probe was called for, in order."""
    return []


@pytest.fixture
def backup_root(tmp_path: Path) -> Path:
    """Root of the per-device backup directories."""
    return tmp_path


@pytest.fixture(autouse=True)
def mock_device_io(
    probe_results: dict[str, bool], probe_calls: list[str], backup_root: Path
) -> Generator[None]:
    """No websocket, a scripted probe and backups under a temporary directory."""

    async def fake_probe(api: ESPSomfyAPI) -> bool:
        probe_calls.append(api.get_host())
        return probe_results.get(api.get_host(), True)

    def fake_backup_dir(api: ESPSomfyAPI) -> str:
        return str(backup_root / f"ESPSomfyRTS_{api.server_id}")

    with (
        patch.object(ESPSomfyController, "ws_connect", return_value=None),
        patch.object(ESPSomfyAPI, "probe", fake_probe),
        patch.object(ESPSomfyAPI, "backup_dir", property(fake_backup_dir)),
    ):
        yield


def _mock_device(aioclient_mock, host: str, server_id: str, hostname: str) -> None:
    """Answer the setup requests of one device."""
    api = f"http://{host}:8081"
    aioclient_mock.get(
        f"{api}/discovery",
        json=DISCOVERY_PAYLOAD | {"serverId": server_id, "hostname": hostname},
    )
    aioclient_mock.put(f"{api}/login", json={"success": True, "apiKey": "0123456789"})
    aioclient_mock.get(f"{api}/shades", json=[])
    aioclient_mock.get(f"{api}/groups", json=[])


async def _setup(
    hass: HomeAssistant,
    aioclient_mock,
    *,
    options: dict[str, Any] | None = None,
    second_device: bool = False,
) -> list[MockConfigEntry]:
    """Set up one device, or two side by side."""
    devices = [(HOST, SERVER_ID, "ESPSomfyRTS")]
    if second_device:
        devices.append((OTHER_HOST, OTHER_SERVER_ID, "ESPSomfyRTS-Garage"))
    entries = []
    for host, server_id, hostname in devices:
        _mock_device(aioclient_mock, host, server_id, hostname)
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_HOST: host},
            options=options or {},
            unique_id=f"espsomfy_{server_id}",
        )
        entry.add_to_hass(hass)
        entries.append(entry)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    return entries


def _entity_id(hass: HomeAssistant, platform: str, key: str, server_id: str) -> str:
    """Entity id from the unique id, whatever name the device got."""
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{key}_espsomfy_{server_id}"
    )
    assert entity_id is not None
    return entity_id


async def _settle(hass: HomeAssistant) -> None:
    """Let the background probe task run what it was woken up for."""
    for _ in range(5):
        await asyncio.sleep(0)
    await hass.async_block_till_done()


async def _elapse(hass: HomeAssistant, delta: timedelta) -> None:
    """Make `delta` pass for every timer, the probe interval included."""
    async_fire_time_changed(hass, dt_util.utcnow() + delta)
    await _settle(hass)


def _make_backups(backup_dir: Path, count: int) -> list[Path]:
    """Create `count` backup files, oldest first, one hour apart."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    now = dt_util.utcnow().timestamp()
    files = []
    for index in range(count):
        path = backup_dir / f"2026-01-01T00_00_{index:02d}.backup"
        path.write_bytes(b"old")
        mtime = now - (count - index) * 3600
        os.utime(path, (mtime, mtime))
        files.append(path)
    return files


async def _backup(hass: HomeAssistant, server_id: str = SERVER_ID) -> None:
    """Call the backup entity service on a device."""
    await hass.services.async_call(
        DOMAIN,
        "backup",
        {"entity_id": _entity_id(hass, "button", "backup", server_id)},
        blocking=True,
    )


# --- 1. and 2. Connectivity --------------------------------------------------


async def test_unplugged_device_goes_off_then_back_on(
    hass: HomeAssistant,
    aioclient_mock,
    probe_results: dict[str, bool],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unplugged: off within 90 s, plugged back: on within 90 s, logged once each."""
    caplog.set_level(logging.INFO, logger="custom_components.espsomfy_rts_enhanced")
    [entry] = await _setup(hass, aioclient_mock)
    controller = entry.runtime_data
    entity_id = _entity_id(hass, "binary_sensor", "connectivity", SERVER_ID)

    controller.ws_onopen()
    await _settle(hass)
    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert state.attributes["websocket_connected"] is True
    assert state.attributes["ws_reconnects"] == 0
    assert state.attributes["last_probe_ok"] is not None

    # Unplugged: the HTTP API stops answering. The websocket heartbeat would
    # also drop the socket, but the probe alone must be enough.
    caplog.clear()
    probe_results[HOST] = False
    await _elapse(hass, DETECTION_BUDGET)
    state = hass.states.get(entity_id)
    assert state.state == STATE_OFF
    # The entity stays available: the state is the information.
    assert state.attributes["websocket_connected"] is True

    # Every failed probe after that stays quiet.
    await _elapse(hass, DETECTION_BUDGET)
    await _elapse(hass, DETECTION_BUDGET)
    controller.ws_onclose()
    for _ in range(3):
        controller.ws_onerror(OSError("unreachable"))
    await _settle(hass)
    records = [r for r in caplog.records if r.name.startswith("custom_components")]
    assert [r.levelno for r in records if r.levelno >= logging.INFO] == [
        logging.WARNING
    ]
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]

    # Plugged back: the socket reconnects, which triggers an immediate probe.
    caplog.clear()
    probe_results[HOST] = True
    controller.ws_onopen()
    await _settle(hass)
    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert state.attributes["ws_reconnects"] == 1
    records = [r for r in caplog.records if r.name.startswith("custom_components")]
    assert [r.levelno for r in records if r.levelno >= logging.INFO] == [logging.INFO]


async def test_http_down_with_websocket_up_is_off(
    hass: HomeAssistant, aioclient_mock, probe_results: dict[str, bool]
) -> None:
    """A websocket alive but an API that no longer answers is not connected."""
    [entry] = await _setup(hass, aioclient_mock)
    entry.runtime_data.ws_onopen()
    entity_id = _entity_id(hass, "binary_sensor", "connectivity", SERVER_ID)

    probe_results[HOST] = False
    await _elapse(hass, timedelta(seconds=PROBE_INTERVAL + 1))
    assert hass.states.get(entity_id).state == STATE_OFF

    # The API answers again, the socket never dropped: back on at next probe.
    probe_results[HOST] = True
    await _elapse(hass, timedelta(seconds=PROBE_INTERVAL + 1))
    assert hass.states.get(entity_id).state == STATE_ON


async def test_websocket_down_with_http_up_is_off(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """The socket dropping is enough, without waiting for a probe."""
    [entry] = await _setup(hass, aioclient_mock)
    entry.runtime_data.ws_onopen()
    entity_id = _entity_id(hass, "binary_sensor", "connectivity", SERVER_ID)
    assert hass.states.get(entity_id).state == STATE_ON

    entry.runtime_data.ws_onclose()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == STATE_OFF
    assert state.attributes["websocket_connected"] is False


async def test_several_devices_are_independent(
    hass: HomeAssistant, aioclient_mock, probe_results: dict[str, bool]
) -> None:
    """Two devices in one Home Assistant: one going down leaves the other on."""
    first, second = await _setup(hass, aioclient_mock, second_device=True)
    first.runtime_data.ws_onopen()
    second.runtime_data.ws_onopen()
    first_id = _entity_id(hass, "binary_sensor", "connectivity", SERVER_ID)
    second_id = _entity_id(hass, "binary_sensor", "connectivity", OTHER_SERVER_ID)
    assert first_id != second_id

    probe_results[OTHER_HOST] = False
    await _elapse(hass, DETECTION_BUDGET)
    assert hass.states.get(first_id).state == STATE_ON
    assert hass.states.get(second_id).state == STATE_OFF


async def test_probe_stops_on_unload_even_while_reconnecting(
    hass: HomeAssistant, aioclient_mock, probe_calls: list[str]
) -> None:
    """Unloading the entry cancels the probe, the socket being down or not."""
    [entry] = await _setup(hass, aioclient_mock)
    controller = entry.runtime_data
    controller.ws_onopen()
    controller.ws_onclose()  # the listener is now in its reconnect backoff
    probe_task = controller._probe_task
    assert probe_task is not None and not probe_task.done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert probe_task.done()

    calls = len(probe_calls)
    await _elapse(hass, DETECTION_BUDGET)
    assert len(probe_calls) == calls


async def test_probe_falls_back_to_discovery_on_older_firmware(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """/rooms is preferred, /discovery is used when the firmware lacks it."""
    api_url = f"http://{HOST}:8081"
    api = ESPSomfyAPI(hass, "entry", {CONF_HOST: HOST})

    aioclient_mock.get(f"{api_url}/rooms", json=[])
    assert await REAL_PROBE(api) is True

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{api_url}/rooms", status=404)
    aioclient_mock.get(f"{api_url}/discovery", json=DISCOVERY_PAYLOAD)
    assert await REAL_PROBE(api) is True
    assert await REAL_PROBE(api) is True
    # Once switched, /rooms is not asked again.
    assert [str(call[1]) for call in aioclient_mock.mock_calls] == [
        f"{api_url}/rooms",
        f"{api_url}/discovery",
        f"{api_url}/discovery",
    ]

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{api_url}/discovery", exc=TimeoutError())
    assert await REAL_PROBE(api) is False


# --- 3. to 6. Backups ---------------------------------------------------------


async def test_backup_of_an_offline_device_fails_without_request(
    hass: HomeAssistant,
    aioclient_mock,
    backup_root: Path,
    probe_results: dict[str, bool],
) -> None:
    """Device off: HomeAssistantError, no request sent, no file deleted."""
    [entry] = await _setup(hass, aioclient_mock)
    entry.runtime_data.ws_onopen()
    files = _make_backups(backup_root / f"ESPSomfyRTS_{SERVER_ID}", 7)

    probe_results[HOST] = False
    entry.runtime_data.ws_onclose()
    await _elapse(hass, DETECTION_BUDGET)
    aioclient_mock.clear_requests()

    with pytest.raises(HomeAssistantError) as err:
        await _backup(hass)
    assert err.value.translation_key == "backup_failed"
    assert aioclient_mock.call_count == 0
    assert all(path.exists() for path in files)


async def test_backup_rejected_by_the_device(
    hass: HomeAssistant,
    aioclient_mock,
    backup_root: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """HTTP error on /backup: HomeAssistantError, no rotation, one ERROR."""
    [entry] = await _setup(hass, aioclient_mock)
    entry.runtime_data.ws_onopen()
    files = _make_backups(backup_root / f"ESPSomfyRTS_{SERVER_ID}", 7)
    aioclient_mock.get(f"http://{HOST}:8081/backup", status=500, text="busy")

    caplog.clear()
    with pytest.raises(HomeAssistantError) as err:
        await _backup(hass)
    assert err.value.translation_key == "backup_failed"
    assert all(path.exists() for path in files)
    assert len([r for r in caplog.records if r.levelno >= logging.ERROR]) == 1


async def test_successful_backup_rotates_and_updates_the_sensor(
    hass: HomeAssistant, aioclient_mock, backup_root: Path
) -> None:
    """Written owner-only, at most N files kept, sensor updated."""
    [entry] = await _setup(hass, aioclient_mock, options={CONF_MAX_BACKUPS: 3})
    entry.runtime_data.ws_onopen()
    backup_dir = backup_root / f"ESPSomfyRTS_{SERVER_ID}"
    old = _make_backups(backup_dir, 6)
    aioclient_mock.get(f"http://{HOST}:8081/backup", content=BACKUP_PAYLOAD)
    sensor_id = _entity_id(hass, "sensor", "last_backup", SERVER_ID)

    await _backup(hass)
    await hass.async_block_till_done()

    remaining = sorted(backup_dir.glob("*.backup"), key=os.path.getmtime)
    assert len(remaining) == 3
    newest = remaining[-1]
    assert newest not in old
    assert newest.read_bytes() == BACKUP_PAYLOAD
    # The two most recent old files are kept, the four oldest are gone.
    assert remaining[:2] == old[-2:]
    if sys.platform != "win32":
        assert stat.S_IMODE(newest.stat().st_mode) == 0o600

    state = hass.states.get(sensor_id)
    assert state.state == dt_util.utc_from_timestamp(
        newest.stat().st_mtime
    ).isoformat(timespec="seconds")
    assert state.attributes["backup_count"] == 3


async def test_existing_entry_without_the_option_keeps_five(
    hass: HomeAssistant, aioclient_mock, backup_root: Path
) -> None:
    """An entry created before the option existed keeps the former 5 files."""
    [entry] = await _setup(hass, aioclient_mock)
    assert CONF_MAX_BACKUPS not in entry.options
    entry.runtime_data.ws_onopen()
    backup_dir = backup_root / f"ESPSomfyRTS_{SERVER_ID}"
    _make_backups(backup_dir, 7)
    aioclient_mock.get(f"http://{HOST}:8081/backup", content=BACKUP_PAYLOAD)

    await _backup(hass)

    assert len(list(backup_dir.glob("*.backup"))) == DEFAULT_MAX_BACKUPS == 5


async def test_last_backup_sensor_reads_the_disk_at_startup(
    hass: HomeAssistant, aioclient_mock, backup_root: Path
) -> None:
    """The sensor starts from the newest file already on disk."""
    files = _make_backups(backup_root / f"ESPSomfyRTS_{SERVER_ID}", 2)
    await _setup(hass, aioclient_mock)

    state = hass.states.get(_entity_id(hass, "sensor", "last_backup", SERVER_ID))
    assert state.state == dt_util.utc_from_timestamp(
        files[-1].stat().st_mtime
    ).isoformat(timespec="seconds")
    assert state.attributes["backup_count"] == 2
