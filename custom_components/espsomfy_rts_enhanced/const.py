"""Constants for the ESPSomfy RTS integration."""

from homeassistant.const import Platform

VERSION = "v3.1.0"
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
