"""The ESPSomfy RTS integration."""

from __future__ import annotations

from enum import IntFlag

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_PIN,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry

from .const import PLATFORMS
from .controller import ESPSomfyAPI, ESPSomfyController, LoginError

type ESPSomfyConfigEntry = ConfigEntry[ESPSomfyController]


class ESPSomfyRTSEntityFeature(IntFlag):
    """Supported features of ESPSomfy-RTS Entities."""

    REBOOT = 1
    BACKUP = 2


async def async_setup_entry(hass: HomeAssistant, entry: ESPSomfyConfigEntry) -> bool:
    """Set up ESPSomfy-RTS from a config entry."""
    api = ESPSomfyAPI(hass, entry.entry_id, entry.data)
    controller = ESPSomfyController(entry.entry_id, hass, api)

    entry.runtime_data = controller

    # 1. On récupère la configuration initiale du boîtier
    await api.get_initial()
    if not api.is_configured:
        raise ConfigEntryNotReady(
            f"Could not find ESPSomfy-RTS device with address {api.get_api_url()}"
        )

    # 2. Authentification auprès du boîtier : sans ce login l'apikey reste vide
    #    et tous les appels REST authentifiés renvoient 401.
    try:
        await api.login(
            {
                "username": entry.data.get(CONF_USERNAME, ""),
                "password": entry.data.get(CONF_PASSWORD, ""),
                "pin": entry.data.get(CONF_PIN, ""),
            }
        )
    except LoginError as ex:
        raise ConfigEntryAuthFailed(
            f"Could not log in to ESPSomfy-RTS device at {api.get_api_url()}"
        ) from ex

    hass.config_entries.async_update_entry(entry, title=api.deviceName)

    # Migration des unique_id historiques (typo "ip_addresss" corrigé en v3.0.2),
    # à faire avant le chargement des plateformes pour ne pas orpheliner l'entité.
    await _async_migrate_unique_ids(hass, entry)

    # 3. Les plateformes ne sont chargées qu'une fois le login réussi, sinon un
    #    échec après forward provoquait un double chargement au retry.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _async_ws_close(_: Event) -> None:
        await controller.ws_close()

    # Si Home Assistant s'arrête proprement, on ferme le socket
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_ws_close)
    )
    # Reload automatique quand l'hôte ou les identifiants changent via le flow d'options
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # 4. On lance la connexion WebSocket
    await controller.ws_connect()

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when its data is updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_migrate_unique_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Migrate legacy entity unique ids to their corrected form."""

    @callback
    def _migrate(reg_entry: er.RegistryEntry) -> dict[str, str] | None:
        if reg_entry.unique_id.startswith("ip_addresss_"):
            return {
                "new_unique_id": reg_entry.unique_id.replace(
                    "ip_addresss_", "ip_address_", 1
                )
            }
        return None

    await er.async_migrate_entries(hass, entry.entry_id, _migrate)

async def async_unload_entry(hass: HomeAssistant, entry: ESPSomfyConfigEntry) -> bool:
    """Unload a config entry."""
    controller: ESPSomfyController | None = getattr(entry, "runtime_data", None)
    if controller is not None:
        await controller.ws_close()
        return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Remove a config entry from a device."""
    return True
