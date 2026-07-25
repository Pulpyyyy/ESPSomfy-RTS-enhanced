"""Tests for the ESPSomfy-RTS Enhanced configuration flow."""

from __future__ import annotations

import errno
from unittest.mock import patch

import aiohttp
import pytest

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.espsomfy_rts_enhanced.const import DOMAIN

from .conftest import DISCOVERY_PAYLOAD, DISCOVERY_URL, HOST, LOGIN_URL, SERVER_ID

# What a device that is powered off, unplugged or unreachable actually raises.
# ClientConnectorError, the one aiohttp raises when the socket cannot be
# opened, derives from ClientOSError: it is both a ClientError and an OSError,
# and never a ConnectionError, which is exactly what made the flow blow up.
CONNECTION_ERRORS = [
    aiohttp.ClientOSError(errno.EHOSTUNREACH, "No route to host"),
    aiohttp.ClientConnectionError("Connection closed"),
    aiohttp.ServerTimeoutError("Timeout on reading data from socket"),
    TimeoutError(),
    OSError(errno.ECONNREFUSED, "Connection refused"),
]


async def test_user_flow_creates_the_entry(hass: HomeAssistant, aioclient_mock) -> None:
    """A reachable device is discovered, logged into and stored."""
    aioclient_mock.get(DISCOVERY_URL, json=DISCOVERY_PAYLOAD)
    aioclient_mock.put(LOGIN_URL, json={"success": True, "apiKey": "0123456789"})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]

    with patch(
        "custom_components.espsomfy_rts_enhanced.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: HOST}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == DISCOVERY_PAYLOAD["hostname"]
    assert result["data"] == {CONF_HOST: HOST}
    assert result["result"].unique_id == f"espsomfy_{SERVER_ID}"
    assert len(mock_setup_entry.mock_calls) == 1


@pytest.mark.parametrize("error", CONNECTION_ERRORS, ids=lambda e: type(e).__name__)
async def test_user_flow_reports_an_offline_device(
    hass: HomeAssistant, aioclient_mock, error: Exception
) -> None:
    """An unreachable device asks the user again instead of raising."""
    aioclient_mock.get(DISCOVERY_URL, exc=error)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_rejects_an_invalid_host(hass: HomeAssistant) -> None:
    """A host that is not an address or a hostname never reaches the network."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "not a host"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "invalid_host"}


async def test_user_flow_reports_a_truncated_discovery(
    hass: HomeAssistant, aioclient_mock
) -> None:
    """A device answering without a server id cannot be identified."""
    aioclient_mock.get(DISCOVERY_URL, json={"hostname": "ESPSomfyRTS"})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "discovery_error"}
