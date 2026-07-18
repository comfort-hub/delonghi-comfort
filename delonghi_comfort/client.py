"""High-level async client for a De'Longhi Comfort heater.

Typical use::

    async with aiohttp.ClientSession() as session:
        client = DelonghiComfort(session=session)
        await client.async_login(email, password)
        devices = await client.async_get_devices()
        await client.async_connect(devices[0])
        status = await client.async_get_status()
        await client.async_set_power(True)
        await client.async_close()
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
import logging
from typing import TYPE_CHECKING

from .const import (
    BRIGHTNESS_MAX,
    BRIGHTNESS_MIN,
    IOT_ENDPOINTS,
    SHADOW_CAPABILITIES,
    SHADOW_STATUS,
    Command,
    TemperatureUnit,
)
from .exceptions import AuthenticationError, DelonghiComfortError
from .gigya import GigyaAuth, GigyaCredentials
from .models import Device, MachineCapabilities, MachineStatus
from .mqtt import ShadowConnection
from .rest import async_get_devices

if TYPE_CHECKING:
    import aiohttp

_LOGGER = logging.getLogger(__name__)

StatusListener = Callable[[MachineStatus], None]


class DelonghiComfort:
    """Auth + device discovery + live shadow read + control for one heater."""

    def __init__(
        self,
        *,
        session: aiohttp.ClientSession,
        region: str = "eu",
        credentials: GigyaCredentials | None = None,
    ) -> None:
        """Create a client bound to a shared aiohttp ``session`` and account ``region``."""
        self._session = session
        self._region = region
        self._gigya = GigyaAuth(session)
        self._credentials = credentials
        self._jwt: str | None = None
        self._shadow: ShadowConnection | None = None
        self._listeners: list[StatusListener] = []

    # -- authentication ------------------------------------------------------
    @property
    def credentials(self) -> GigyaCredentials | None:
        """The stored Gigya session (persist this to avoid re-entering the password)."""
        return self._credentials

    @property
    def jwt(self) -> str | None:
        """The most recently minted JWT."""
        return self._jwt

    async def async_login(self, email: str, password: str) -> GigyaCredentials:
        """Log in with a password, storing credentials and minting the first JWT."""
        self._credentials = await self._gigya.login(email, password)
        await self.async_refresh_jwt()
        return self._credentials

    async def async_refresh_jwt(self) -> str:
        """Mint a fresh JWT from stored credentials (rotates the live connection too)."""
        if self._credentials is None:
            raise AuthenticationError("no credentials to refresh the JWT")
        self._jwt = await self._gigya.get_jwt(self._credentials)
        if self._shadow is not None:
            self._shadow.update_jwt(self._jwt)
        return self._jwt

    def _require_jwt(self) -> str:
        if self._jwt is None:
            raise AuthenticationError("not authenticated; call async_login first")
        return self._jwt

    def _require_shadow(self) -> ShadowConnection:
        if self._shadow is None:
            raise DelonghiComfortError("not connected; call async_connect first")
        return self._shadow

    # -- devices -------------------------------------------------------------
    async def async_get_devices(self) -> list[Device]:
        """List appliances on the account."""
        return await async_get_devices(self._session, self._require_jwt(), self._region)

    # -- live connection -----------------------------------------------------
    async def async_connect(self, device: Device | str) -> None:
        """Open the MQTT shadow/command connection for a device (or thing name)."""
        thing = device.thing_name if isinstance(device, Device) else device
        self._shadow = ShadowConnection(
            thing_name=thing,
            jwt=self._require_jwt(),
            endpoint=IOT_ENDPOINTS[self._region],
        )
        self._shadow.add_listener(self._on_reported)
        await self._shadow.start()

    async def async_close(self) -> None:
        """Close the MQTT connection (leaves the shared aiohttp session untouched)."""
        if self._shadow is not None:
            with suppress(Exception):
                await self._shadow.stop()
            self._shadow = None

    def add_status_listener(self, callback: StatusListener) -> Callable[[], None]:
        """Register a callback invoked with a ``MachineStatus`` on every live update."""
        self._listeners.append(callback)

        def _remove() -> None:
            with suppress(ValueError):
                self._listeners.remove(callback)

        return _remove

    def _on_reported(self, reported: dict[str, object]) -> None:
        status = MachineStatus.from_reported(dict(reported))
        for listener in list(self._listeners):
            try:
                listener(status)
            except Exception:  # noqa: BLE001 - a consumer callback must not stop others
                _LOGGER.exception("status listener raised; continuing")

    # -- state read ----------------------------------------------------------
    async def async_get_status(self) -> MachineStatus:
        """Fetch the current ``MachineStatus`` shadow."""
        reported = await self._require_shadow().async_get_shadow(SHADOW_STATUS)
        return MachineStatus.from_reported(reported)

    async def async_get_capabilities(self) -> MachineCapabilities:
        """Fetch the static ``MachineCapabilities`` shadow."""
        reported = await self._require_shadow().async_get_shadow(SHADOW_CAPABILITIES)
        return MachineCapabilities.from_reported(reported)

    # -- control -------------------------------------------------------------
    async def async_command(self, command: Command, value: int | str) -> None:
        """Send an arbitrary command and wait for the device acknowledgement."""
        await self._require_shadow().async_send_command(command.value, value)

    async def async_set_power(self, on: bool) -> None:
        """Turn the heater on or off."""
        await self.async_command(Command.POWER, 1 if on else 0)

    async def async_set_temperature(
        self, value: int, unit: TemperatureUnit = TemperatureUnit.CELSIUS
    ) -> None:
        """Set the target temperature in whole degrees of the given display unit.

        The device takes the setpoint in whatever unit it currently displays, via
        a separate ``SetRoomTempRequest_degC`` / ``SetRoomTempRequest_degF`` command.
        """
        command = (
            Command.TEMPERATURE_C
            if unit is TemperatureUnit.CELSIUS
            else Command.TEMPERATURE_F
        )
        await self.async_command(command, int(value))

    async def async_set_eco(self, on: bool) -> None:
        """Enable or disable Eco (power-limit) mode."""
        await self.async_command(Command.ECO, 1 if on else 0)

    async def async_set_child_lock(self, on: bool) -> None:
        """Enable or disable the child lock."""
        await self.async_command(Command.CHILD_LOCK, 1 if on else 0)

    async def async_set_night_mode(self, on: bool) -> None:
        """Enable or disable night mode."""
        await self.async_command(Command.NIGHT_MODE, 1 if on else 0)

    async def async_set_silent(self, on: bool) -> None:
        """Enable or disable silent mode."""
        await self.async_command(Command.SILENT, 1 if on else 0)

    async def async_set_schedule_enabled(self, on: bool) -> None:
        """Enable or disable the device's on-board weekly schedule."""
        await self.async_command(Command.SCHEDULE_ENABLE, 1 if on else 0)

    async def async_set_temp_unit(self, unit: TemperatureUnit) -> None:
        """Set the heater's display temperature unit.

        The wire value is inverted relative to the reported ``TempUnit`` flag
        (verified on hardware): the device takes ``0`` for Celsius and ``1`` for
        Fahrenheit, whereas ``TempUnit`` reports ``True`` for Celsius.
        """
        value = 0 if unit is TemperatureUnit.CELSIUS else 1
        await self.async_command(Command.TEMP_UNIT, value)

    async def async_set_brightness(self, level: int) -> None:
        """Set the LED ring brightness (0-3)."""
        if not BRIGHTNESS_MIN <= level <= BRIGHTNESS_MAX:
            raise ValueError(f"brightness must be {BRIGHTNESS_MIN}-{BRIGHTNESS_MAX}")
        await self.async_command(Command.BRIGHTNESS, level)
