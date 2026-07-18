"""Constants and protocol identifiers for the De'Longhi Comfort (Daedalus) cloud.

All API keys / endpoints here are app-global public client identifiers extracted from
the public `com.delonghigroup.comfort` APK — the equivalent of OAuth client IDs, shared
by every install. They are not per-user secrets.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

# --- Gigya (SAP CDC) identity ------------------------------------------------
GIGYA_BASE_URL: Final = "https://accounts.eu1.gigya.com"

# One Gigya apiKey per account pool. The library auto-probes these in order.
GIGYA_API_KEYS: Final[dict[str, str]] = {
    "COMFORT_EU": "4_VTLGz33ylwYVesXKstwnXw",
    "EU_US": "3_e5qn7USZK-QtsIso1wCelqUKAK_IVEsYshRIssQ-X-k55haiZXmKWDHDRul2e5Y2",
    "CH": "3_WP_c8OVu_yOoqYXN3Dq-Oi7nNkbS2bwqS3rQXJ6SPkodgE4FOpyuE_UVlrCuSGEm",
}

# getJWT expiration (seconds). 90 days — the app default.
JWT_EXPIRATION_SECONDS: Final = 90 * 24 * 60 * 60

# --- AWS API Gateway (REST) --------------------------------------------------
# The device registry endpoint. `GET devices` is authorized by the Gigya JWT as a
# Bearer token (a Lambda authorizer), NOT SigV4.
REST_BASE_URLS: Final[dict[str, str]] = {
    "eu": "https://8q8c9xktb0.execute-api.eu-central-1.amazonaws.com/dlg-prod/",
    "us": "https://gax54h1o65.execute-api.us-east-1.amazonaws.com/dlg-prod/",
}
# Sent as the `source` header on every REST/command call.
SOURCE: Final = "comfort"
# Sent as `AppId` inside every command payload.
APP_ID: Final = "Comfort"

# --- AWS IoT Core (MQTT 5 over TLS:443, ALPN "mqtt") -------------------------
# Custom Lambda token authorizer; the Gigya JWT is the MQTT password.
IOT_ENDPOINTS: Final[dict[str, str]] = {
    "eu": "a2612mo23mfrw1-ats.iot.eu-central-1.amazonaws.com",
    "us": "a23n13fd13p6h-ats.iot.us-east-1.amazonaws.com",
}
IOT_PORT: Final = 443
IOT_AUTHORIZER: Final = "dlg-prod-token-authorizer"

# Regions to search during discovery (probe order; eu first — most accounts).
SUPPORTED_REGIONS: Final[tuple[str, ...]] = ("eu", "us")

# Named AWS IoT shadows the device maintains.
SHADOW_STATUS: Final = "MachineStatus"
SHADOW_CAPABILITIES: Final = "MachineCapabilities"

# Default polling / request timeouts (seconds).
COMMAND_TIMEOUT: Final = 15.0
STATUS_TIMEOUT: Final = 15.0


class TemperatureUnit(StrEnum):
    """The heater's display temperature unit.

    Mirrors Home Assistant's ``UnitOfTemperature`` so a consumer can map between
    the two without this framework-agnostic library importing Home Assistant.
    """

    CELSIUS = "C"
    FAHRENHEIT = "F"


class Command(StrEnum):
    """`Message` names published to `<thing>/commands/request` to control the heater.

    Each maps to the reported ``MachineStatus`` field it changes (see ``COMMAND_FIELDS``).
    """

    POWER = "SetDeviceStatusRequest"
    TEMPERATURE_C = "SetRoomTempRequest_degC"
    TEMPERATURE_F = "SetRoomTempRequest_degF"
    ECO = "SetEcoModeRequest"
    CHILD_LOCK = "SetLockModeRequest"
    NIGHT_MODE = "SetNightModeRequest"
    BRIGHTNESS = "SetBrightnessLevelRequest"
    SILENT = "SetSoundRequest"
    SCHEDULE_ENABLE = "SetScheduleEnRequest"
    TEMP_UNIT = "SetTempUnitRequest"
    TMZONE = "SetTMZoneRequest"


# Command -> the reported MachineStatus field it drives.
COMMAND_FIELDS: Final[dict[Command, str]] = {
    Command.POWER: "DeviceStatus",
    Command.TEMPERATURE_C: "TempSetPoint",
    Command.TEMPERATURE_F: "TempSetPoint",
    Command.ECO: "PowerLimit",
    Command.CHILD_LOCK: "KeyLock",
    Command.NIGHT_MODE: "NightModeEnable",
    Command.BRIGHTNESS: "BrightnessLevel",
    Command.SILENT: "SilentEnable",
    Command.SCHEDULE_ENABLE: "ScheduleEnable",
    Command.TEMP_UNIT: "TempUnit",
    Command.TMZONE: "TMZone",
}

# RoomTemp / PCB temps are reported as tenths of a degree; setpoint is whole degrees.
TEMP_SCALE: Final = 10
BRIGHTNESS_MIN: Final = 0
BRIGHTNESS_MAX: Final = 3


def shadow_topic(thing_name: str, shadow: str, verb: str) -> str:
    """Build a named-shadow topic, e.g. ``$aws/things/<t>/shadow/name/MachineStatus/get``."""
    return f"$aws/things/{thing_name}/shadow/name/{shadow}/{verb}"


def command_request_topic(thing_name: str) -> str:
    """Topic to publish control commands to."""
    return f"{thing_name}/commands/request"


def command_response_topic(thing_name: str) -> str:
    """Topic the device replies to commands on."""
    return f"{thing_name}/commands/response"
