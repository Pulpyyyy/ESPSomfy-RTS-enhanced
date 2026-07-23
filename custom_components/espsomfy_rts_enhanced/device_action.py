"""Provides device actions for ESPSomfy-RTS."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.components.device_automation import (
    async_validate_entity_schema,
    toggle_entity,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_TYPE,
)
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType, TemplateVarsType

from .const import DOMAIN

# NOTE: l'action "restore" de l'amont rstrouse n'a jamais été terminée (schéma
# jamais enregistré, branche d'exécution commentée là-bas aussi) — retirée ici.

ONOFF_SCHEMA = toggle_entity.ACTION_SCHEMA.extend({vol.Required(CONF_DOMAIN): DOMAIN})

_ACTION_SCHEMA = cv.DEVICE_ACTION_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In({"Reboot", "Backup"}),
        vol.Required(CONF_ENTITY_ID): cv.entity_id_or_uuid,
    }
)


async def async_validate_action_config(
    hass: HomeAssistant, config: ConfigType
) -> ConfigType:
    """Validate config."""
    return async_validate_entity_schema(hass, config, _ACTION_SCHEMA)


async def async_get_actions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List device actions for ESPSomfy-RTS devices."""
    actions = await toggle_entity.async_get_actions(hass, device_id, DOMAIN)
    registry = er.async_get(hass)
    for entry in er.async_entries_for_device(registry, device_id):
        # 🟢 CORRECTION : Détection basée sur la fin de l'entity_id suite au changement de norme de nommage
        if entry.entity_id.startswith("button.") and entry.entity_id.endswith("_reboot"):
            actions.append(
                {
                    CONF_DEVICE_ID: device_id,
                    CONF_DOMAIN: DOMAIN,
                    CONF_ENTITY_ID: entry.entity_id,
                    CONF_TYPE: "Reboot",
                }
            )
        elif entry.entity_id.startswith("button.") and entry.entity_id.endswith("_backup"):
            actions.append(
                {
                    CONF_DEVICE_ID: device_id,
                    CONF_DOMAIN: DOMAIN,
                    CONF_ENTITY_ID: entry.entity_id,
                    CONF_TYPE: "Backup",
                }
            )

    return actions


async def async_call_action_from_config(
    hass: HomeAssistant,
    config: ConfigType,
    variables: TemplateVarsType,
    context: Context | None,
) -> None:
    """Execute a device action."""
    if config[CONF_TYPE] == "Backup":
        await hass.services.async_call(
            DOMAIN,
            "backup",
            {
                ATTR_ENTITY_ID: config[CONF_ENTITY_ID],
            },
            blocking=True,
            context=context,
        )
    elif config[CONF_TYPE] == "Reboot":
        await hass.services.async_call(
            DOMAIN,
            "reboot",
            {
                ATTR_ENTITY_ID: config[CONF_ENTITY_ID],
            },
            blocking=True,
            context=context,
        )
    else:
        return await toggle_entity.async_call_action_from_config(
            hass, config, variables, context, DOMAIN
        )


async def async_get_action_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """List action capabilities."""
    return {}
