"""Support for ESPSomfy RTS updates."""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import EVT_CONNECTED, EVT_FWSTATUS, EVT_UPDPROGRESS
from .controller import ESPSomfyController
from .entity import ESPSomfyEntity

_LOGGER = logging.getLogger(__name__)


def _supported_features(
    check_for_update: bool, internet_available: bool
) -> UpdateEntityFeature:
    """Return the update features the device currently offers.

    Installing needs the device to look for updates and to be able to reach the
    internet, it downloads the firmware itself.
    """
    features = (
        UpdateEntityFeature.SPECIFIC_VERSION
        | UpdateEntityFeature.PROGRESS
        | UpdateEntityFeature.RELEASE_NOTES
    )
    if check_for_update and internet_available:
        features |= UpdateEntityFeature.INSTALL | UpdateEntityFeature.BACKUP
    return features


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ESPSomfy RTS update based on a config entry."""
    controller: ESPSomfyController = config_entry.runtime_data
    data = controller.api.get_config()
    if "serverId" in data:
        async_add_entities([ESPSomfyRTSUpdateEntity(controller=controller)])


class ESPSomfyRTSUpdateEntity(ESPSomfyEntity, UpdateEntity):
    """Defines an ESPSomfy RTS update entity."""
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_entity_category = EntityCategory.CONFIG

    # Push only entity: Home Assistant must not refresh it on its own.
    _attr_should_poll = False

    _attr_has_entity_name = True
    _attr_translation_key = "firmware"

    def __init__(self, *, controller: ESPSomfyController) -> None:
        """Initialize the update entity."""
        super().__init__(data=None, controller=controller)

        self._controller = controller
        self._available = True
        self._attr_unique_id = f"update_{controller.unique_id}"
        self._update_status = 0
        self._fw_progress = 100
        self._app_progress = 100
        self._total_progress = 100

        # The device already told us during discovery whether it looks for
        # updates and whether it has internet, so the install button does not
        # have to wait for the first fwStatus event to appear.
        self._attr_supported_features = _supported_features(
            controller.check_for_update, controller.internet_available
        )

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if not self.enabled:
            return
        evt = self._controller.data.get("event", "")
        if evt == EVT_CONNECTED and "connected" in self._controller.data:
            self._available = bool(self._controller.data["connected"])
            self.async_write_ha_state()

        elif evt == EVT_FWSTATUS:
            evt_data = self._controller.data

            # Debug and not error: this is a routine event, not a failure.
            _LOGGER.debug("ESPSomfy RTS FWSTATUS Payload: %s", evt_data)

            # The install button only lights up when the device confirms both
            # conditions, otherwise the download would fail on the device.
            self._attr_supported_features = _supported_features(
                evt_data.get("checkForUpdate", False),
                evt_data.get("inetAvailable", False),
            )
            self.async_write_ha_state()

        elif evt == EVT_UPDPROGRESS:
            d = self._controller.data
            if "part" in d:
                # A device that reports a zero sized image has nothing to show
                # and must not divide by it.
                total = int(d.get("total", 0))
                if total <= 0:
                    return
                progress = (int(d.get("loaded", 0)) / total) * 100
                if int(d["part"]) == 0:
                    self._app_progress = 0
                    self._fw_progress = progress
                elif int(d["part"]) == 100:
                    self._fw_progress = 100
                    self._app_progress = progress
                self._total_progress = int((self._fw_progress + self._app_progress) / 2)
                self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Indicates whether the shade is available."""
        return self._available

    @property
    def can_install(self) -> bool:
        """Indicates whether an update could actually be installed right now."""
        if not self._controller.can_update:
            # Firmware older than 2.2.1 has no download endpoint.
            return False
        if not self.supported_features & UpdateEntityFeature.INSTALL:
            return False
        return self.latest_version is not None

    @property
    def installed_version(self) -> str | None:
        """Version currently installed and in use."""
        if (version := self._controller.version) is None:
            return None
        return str(version)

    @property
    def latest_version(self) -> str | None:
        """Latest version available for install."""
        cfg = self._controller.api.get_config()
        if cfg.get("checkForUpdate", False) is False:
            return None

        if (latest := self._controller.latest_version) is None:
            return None
        return str(latest)

    @property
    def in_progress(self) -> bool | int | None:
        """Update installation progress."""
        if self._total_progress < 100:
            return self._total_progress
        return False

    @property
    def release_url(self) -> str | None:
        """URL to the full release notes of the latest version available."""
        if (version := self.latest_version) is None:
            return None
        return f"https://github.com/Pulpyyyy/ESPSomfy-RTS/releases/tag/{version}"

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Install an update."""
        success = True
        if backup:
            success = await self._controller.create_backup()
        if success:
            # Honour the requested version (SPECIFIC_VERSION), else the latest.
            version = version or cast(str, self.latest_version)
            if version is not None:
                await self.controller.update_firmware(version)

    async def async_release_notes(self) -> str | None:
        """Return the release notes from GitHub."""
        if (version := self.latest_version) is None:
            return None

        return await self._controller.fetch_release_notes(version)

    async def async_update(self) -> None:
        """Update the entity state.

        Overridden to prevent Home Assistant from polling the coordinator
        and triggering a NotImplementedError.
        """
        pass
