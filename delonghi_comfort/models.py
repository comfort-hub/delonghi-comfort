"""Typed models for devices, live status and capabilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .const import TEMP_SCALE, TemperatureUnit


def _metadata_timestamp(entry: Any) -> datetime | None:
    """Extract a UTC datetime from a shadow-metadata entry's epoch ``timestamp``.

    AWS IoT records each reported field's last-update time under
    ``metadata.reported.<field>.timestamp`` (epoch seconds). Anything else — a
    missing/non-numeric timestamp, or a nested (structured-field) entry that has no
    top-level timestamp — yields ``None`` rather than raising.
    """
    if not isinstance(entry, dict):
        return None
    ts = entry.get("timestamp")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return None
    return datetime.fromtimestamp(ts, tz=UTC)


@dataclass(frozen=True, slots=True)
class Device:
    """A paired appliance as returned by ``GET devices``."""

    thing_name: str
    """AWS IoT thing name / ``machineName`` — the id used for all MQTT topics."""
    serial_number: str
    """De'Longhi serial number (the Wi-Fi MAC, e.g. ``90:70:69:90:93:74``)."""
    model: str
    sku: str
    online: bool
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Device:
        """Build a ``Device`` from one ``ownedByMe`` / ``sharedToMe`` entry."""
        return cls(
            thing_name=str(data.get("machineName", "")),
            serial_number=str(data.get("serialNumber", "")),
            model=str(data.get("machineModel", "")),
            sku=str(data.get("sku", "")),
            online=str(data.get("status", "")).upper() == "ONLINE",
            raw=data,
        )


@dataclass(frozen=True, slots=True)
class MachineStatus:
    """A snapshot of the ``MachineStatus`` shadow ``reported`` state.

    Unknown/extra fields are preserved in ``raw`` so new firmware fields never break parsing.
    """

    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_reported(
        cls, reported: dict[str, Any], metadata: dict[str, Any] | None = None
    ) -> MachineStatus:
        """Build a status snapshot from a shadow ``state.reported`` dict.

        ``metadata`` is the shadow's ``metadata.reported`` sub-document (per-field
        ``{"timestamp": <epoch seconds>}`` entries). It records how fresh each
        reported value is — see :meth:`reported_at` / :attr:`last_reported_at`.
        """
        return cls(raw=dict(reported), metadata=dict(metadata or {}))

    def reported_at(self, key: str) -> datetime | None:
        """When the device last reported ``key`` (from shadow metadata), or ``None``."""
        return _metadata_timestamp(self.metadata.get(key))

    @property
    def last_reported_at(self) -> datetime | None:
        """The most recent per-field report time across the shadow, or ``None``.

        This is how fresh the shadow document is overall: an old value means the
        device has not reported for a while (e.g. it is switched off), so consumers
        can flag the reading as stale rather than trust it.
        """
        stamps = [
            ts
            for ts in (_metadata_timestamp(entry) for entry in self.metadata.values())
            if ts is not None
        ]
        return max(stamps) if stamps else None

    def _get(self, key: str) -> Any:
        return self.raw.get(key)

    def _get_int(self, key: str) -> int | None:
        """Coerce a numeric field to int, treating bool/garbage as missing.

        ``bool`` is a subclass of ``int``, so a stray ``True``/``False`` in the
        shadow must be rejected rather than silently reported as ``1``/``0``.
        """
        value = self._get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return int(value)

    @property
    def is_on(self) -> bool:
        """Whether the heater is powered on (``DeviceStatus == 1``)."""
        return bool(self._get("DeviceStatus") == 1)

    @property
    def target_temperature(self) -> int | None:
        """Target temperature in whole degrees (``TempSetPoint``)."""
        value = self._get("TempSetPoint")
        return int(value) if isinstance(value, (int, float)) else None

    @property
    def current_temperature(self) -> float | None:
        """Measured room temperature in degrees (``RoomTemp`` is reported in tenths)."""
        value = self._get("RoomTemp")
        return value / TEMP_SCALE if isinstance(value, (int, float)) else None

    @property
    def eco(self) -> bool:
        """Eco / power-limit mode (``PowerLimit``)."""
        return bool(self._get("PowerLimit"))

    @property
    def child_lock(self) -> bool:
        """Child lock (``KeyLock``)."""
        return bool(self._get("KeyLock"))

    @property
    def night_mode(self) -> bool:
        """Night mode (``NightModeEnable``)."""
        return bool(self._get("NightModeEnable"))

    @property
    def silent(self) -> bool:
        """Silent mode (``SilentEnable``)."""
        return bool(self._get("SilentEnable"))

    @property
    def schedule_enabled(self) -> bool:
        """Weekly schedule enabled (``ScheduleEnable``)."""
        return bool(self._get("ScheduleEnable"))

    @property
    def brightness(self) -> int | None:
        """LED ring brightness level 0-3 (``BrightnessLevel``)."""
        value = self._get("BrightnessLevel")
        return int(value) if isinstance(value, (int, float)) else None

    @property
    def celsius(self) -> bool:
        """Whether the display unit is Celsius (``TempUnit``)."""
        return bool(self._get("TempUnit"))

    @property
    def temperature_unit(self) -> TemperatureUnit:
        """The display temperature unit (``TempUnit``: ``True`` = Celsius)."""
        return TemperatureUnit.CELSIUS if self.celsius else TemperatureUnit.FAHRENHEIT

    @property
    def lan_ip(self) -> str | None:
        """The heater's LAN IP as it reports it (``LanIpAddress``)."""
        value = self._get("LanIpAddress")
        return str(value) if value else None

    @property
    def on_off_timer_minutes(self) -> int | None:
        """Configured on/off timer duration in minutes (``OnOffTimerMinutes``)."""
        return self._get_int("OnOffTimerMinutes")

    @property
    def timer_remaining(self) -> int | None:
        """Minutes left on the running timer (``TimerRemain``)."""
        return self._get_int("TimerRemain")

    @property
    def timer_active(self) -> bool:
        """Whether a timer is currently counting down (``TimerStatus``)."""
        value = self._get("TimerStatus")
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        return False

    @property
    def ota_progress(self) -> int | None:
        """Firmware OTA download progress percent (``OTAdownloadCompleteness``)."""
        return self._get_int("OTAdownloadCompleteness")

    @property
    def running_partition(self) -> int | None:
        """Active firmware partition index (``RunningPartition``)."""
        return self._get_int("RunningPartition")

    @property
    def alarms(self) -> dict[str, bool]:
        """The fault-flag map (``alarms``)."""
        value = self._get("alarms")
        return {k: bool(v) for k, v in value.items()} if isinstance(value, dict) else {}

    @property
    def any_alarm(self) -> bool:
        """True if any alarm/fault flag is set."""
        return any(self.alarms.values())


@dataclass(frozen=True, slots=True)
class MachineCapabilities:
    """Static device capabilities from the ``MachineCapabilities`` shadow."""

    mac: str
    serial_number: str
    model: str
    sku: str
    wifi_firmware: str
    aws_version: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_reported(cls, reported: dict[str, Any]) -> MachineCapabilities:
        """Build capabilities from a shadow ``state.reported`` dict."""
        return cls(
            mac=str(reported.get("MAC", "")),
            serial_number=str(reported.get("SN", "")),
            model=str(reported.get("MachineModel", "")),
            sku=str(reported.get("SKU", "")),
            wifi_firmware=str(reported.get("FWWiFiVersion", "")),
            aws_version=str(reported.get("DLAWS_Version", "")),
            raw=dict(reported),
        )
