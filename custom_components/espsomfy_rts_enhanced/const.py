"""Constants for the ESPSomfy RTS integration."""

import json
from pathlib import Path

from homeassistant.const import Platform

# Source de vérité unique : la version vient du manifest (lu à l'import,
# que HA exécute en executor). Plus de désynchro possible entre les deux.
VERSION = "v" + json.loads(
    (Path(__file__).parent / "manifest.json").read_text(encoding="utf-8")
)["version"]
DOMAIN = "espsomfy_rts_enhanced"
MANUFACTURER = "Pulpyyyy"
API_SHADES = "/shades"
API_GROUPS = "/groups"
API_SHADECOMMAND = "/shadeCommand"
API_GROUPCOMMAND = "/groupCommand"
API_TILTCOMMAND = "/tiltCommand"
API_DISCOVERY = "/discovery"
API_LOGIN = "/login"
API_SETPOSITIONS = "/setPositions"
API_SETSENSOR = "/setSensor"
API_BACKUP = "/backup"
API_REBOOT = "/reboot"
EVT_SHADESTATE = "shadeState"
EVT_GROUPSTATE = "groupState"
EVT_GROUPREMOVED = "groupRemoved"
EVT_SHADECOMMAND = "shadeCommand"
EVT_SHADEADDED = "shadeAdded"
EVT_SHADEREMOVED = "shadeRemoved"
EVT_CONNECTED = "connected"
EVT_FWSTATUS = "fwStatus"
EVT_UPDPROGRESS = "updateProgress"
EVT_WIFISTRENGTH = "wifiStrength"
EVT_ETHERNET = "ethernet"
EVT_MEMSTATUS = "memStatus"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.COVER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]
