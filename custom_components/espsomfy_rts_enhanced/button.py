"""Support for ESPSomfy RTS device actions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import os
import glob

from packaging.version import parse as version_parse

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .__init__ import ESPSomfyRTSEntityFeature
from .const import API_REBOOT, DOMAIN, EVT_CONNECTED
from .controller import ESPSomfyController
from .entity import ESPSomfyEntity

SVC_REBOOT = "reboot"
SVC_BACKUP = "backup"


@dataclass
class ESPSomfyButtonDescriptionMixin:
    """Mixin for entity description."""


@dataclass
class ESPSomfyButtonDescription(
    ButtonEntityDescription, ESPSomfyButtonDescriptionMixin
):
    """A base class descriptor for a button entity."""

    id: str | None = None
    events: dict | None = None
    action: dict | None = None
    features: Iterable[int] | None = None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ESPSomfy-RTS update based on a config entry."""
    new_entities = []
    controller: ESPSomfyController = hass.data[DOMAIN][config_entry.entry_id]
    v = version_parse(controller.version)
    if v.major >= 2 and v.minor >= 3 and v.micro >= 0:
        new_entities.append(
            ESPSomfyButton(
                controller=controller,
                cfg=ESPSomfyButtonDescription(
                    key="reboot",
                    translation_key="reboot",
                    has_entity_name=True,
                    entity_category=EntityCategory.CONFIG,
                    device_class=ButtonDeviceClass.RESTART,
                    events={},
                    action={"service": API_REBOOT},
                    features=1,
                    icon="mdi:restart",
                ),
            )
        )
    if v.major >= 1:
        new_entities.append(
            ESPSomfyButton(
                controller=controller,
                cfg=ESPSomfyButtonDescription(
                    key="backup",
                    translation_key="backup",
                    has_entity_name=True,
                    entity_category=EntityCategory.CONFIG,
                    device_class=ButtonDeviceClass.IDENTIFY,
                    events={},
                    action={"apimethod": "create_backup"},
                    features=2,
                    icon="mdi:download",
                ),
            )
        )
    async_add_entities(new_entities)
    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        name=SVC_REBOOT,
        schema={},
        func="async_press",
        required_features=[ESPSomfyRTSEntityFeature.REBOOT],
    )
    platform.async_register_entity_service(
        name=SVC_BACKUP,
        schema={},
        func="async_press",
        required_features=[ESPSomfyRTSEntityFeature.BACKUP],
    )


class ESPSomfyButton(ESPSomfyEntity, ButtonEntity):
    """Defines a reboot entity."""

    _attr_device_class = ButtonDeviceClass.RESTART

    def __init__(
        self, *, controller: ESPSomfyController, cfg: ESPSomfyButtonDescription
    ) -> None:
        """Initialize the reboot entity."""
        super().__init__(data=None, controller=controller)
        self._controller = controller
        self._attr_device_class = cfg.device_class

        # Liaison avec la description
        self.entity_description = cfg

        self._attr_unique_id = f"{cfg.key}_{controller.unique_id}"
        self._attr_entity_category = cfg.entity_category
        self._attr_icon = cfg.icon
        self._available = True
        self._action = cfg.action
        self._attr_assumed_state = True
        self._attr_supported_features = cfg.features

        # Application de la norme Home Assistant
        self._attr_has_entity_name = cfg.has_entity_name
        self._attr_translation_key = cfg.translation_key

    async def async_press(self) -> None:
        """Process the button press."""
        data = None
        if "data" in self._action:
            data = self._action["data"]

        # 1. Exécution de l'action initiale (Reboot ou Sauvegarde)
        if "service" in self._action:
            await self._controller.api.put_command(self._action["service"], data)
        elif "apimethod" in self._action:
            method = getattr(self._controller.api, self._action["apimethod"])
            await method()

        # 2. 🟢 AJOUT : Si c'est le bouton backup, on gère la rotation des 5 fichiers
        if self.entity_description.key == "backup":
            try:
                # On récupère le chemin du dossier des sauvegardes
                # (S'adapte dynamiquement selon l'adresse définie dans ton contrôleur)
                backup_dir = self.hass.config.path(f"ESPSomfyRTS_{self._controller.unique_id}")

                if os.path.exists(backup_dir):
                    # Trouver tous les fichiers .backup dans ce dossier
                    files = glob.glob(os.path.join(backup_dir, "*.backup"))

                    # Trier les fichiers par date de modification (du plus récent au plus vieux)
                    files.sort(key=os.path.getmtime, reverse=True)

                    # Si on a plus de 5 fichiers, on supprime les plus anciens
                    if len(files) > 5:
                        files_to_delete = files[5:]
                        for file_path in files_to_delete:
                            os.remove(file_path)
            except Exception:
                # Sécurité pour éviter de bloquer l'intégration en cas d'erreur de droits sur les fichiers
                pass

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self._controller.data.get("event", "") == EVT_CONNECTED:
            if "connected" in self._controller.data and self._attr_available != bool(
                self._controller.data["connected"]
            ):
                self._attr_available = bool(self._controller.data["connected"])
                self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Indicates whether the shade is available."""
        return self._available
