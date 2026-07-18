"""End-to-end tests for the DelonghiComfort client with fake transports."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import pytest

from delonghi_comfort import Commands, TemperatureUnit
from delonghi_comfort.client import DelonghiComfort
from delonghi_comfort.exceptions import AuthenticationError

from .fakes import FakeResponse, RecordingShadow, make_session

if TYPE_CHECKING:
    from delonghi_comfort.models import MachineStatus

_SECRET = base64.b64encode(b"secret").decode()


def _routes() -> dict[str, FakeResponse]:
    return {
        "accounts.login": FakeResponse(
            json_data={
                "errorCode": 0,
                "sessionInfo": {"sessionToken": "st", "sessionSecret": _SECRET},
            }
        ),
        "accounts.getJWT": FakeResponse(json_data={"id_token": "jwt-token"}),
        "devices": FakeResponse(
            json_data={"ownedByMe": [{"machineName": "THING", "status": "ONLINE"}]}
        ),
    }


async def _logged_in_client() -> DelonghiComfort:
    session = make_session(_routes())
    client = DelonghiComfort(session=session)
    await client.async_login("me@example.com", "pw")
    return client


async def test_login_and_list_devices() -> None:
    """Login mints a JWT and the device list is fetched with it."""
    client = await _logged_in_client()
    assert client.jwt == "jwt-token"
    assert client.credentials is not None
    devices = await client.async_get_devices()
    assert devices[0].thing_name == "THING"


async def test_command_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each convenience method sends the right command message and value."""
    shadow = RecordingShadow()
    monkeypatch.setattr("delonghi_comfort.client.ShadowConnection", lambda **_: shadow)
    client = await _logged_in_client()
    await client.async_connect("THING")

    await client.async_set_power(True)
    await client.async_set_temperature(23)
    await client.async_set_eco(True)
    await client.async_set_child_lock(False)
    await client.async_set_night_mode(True)
    await client.async_set_silent(False)
    await client.async_set_brightness(2)

    assert shadow.commands == [
        ("SetDeviceStatusRequest", 1),
        ("SetRoomTempRequest_degC", 23),
        ("SetEcoModeRequest", 1),
        ("SetLockModeRequest", 0),
        ("SetNightModeRequest", 1),
        ("SetSoundRequest", 0),
        ("SetBrightnessLevelRequest", 2),
    ]


async def test_extended_command_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Schedule-enable and temp-unit setters map to the right commands."""
    shadow = RecordingShadow()
    monkeypatch.setattr("delonghi_comfort.client.ShadowConnection", lambda **_: shadow)
    client = await _logged_in_client()
    await client.async_connect("THING")

    await client.async_set_schedule_enabled(True)
    # The wire value is inverted vs the reported TempUnit flag (verified on
    # hardware): Celsius = 0, Fahrenheit = 1.
    await client.async_set_temp_unit(TemperatureUnit.CELSIUS)
    await client.async_set_temp_unit(TemperatureUnit.FAHRENHEIT)

    assert shadow.commands == [
        ("SetScheduleEnRequest", 1),
        ("SetTempUnitRequest", 0),
        ("SetTempUnitRequest", 1),
    ]


async def test_set_temperature_unit_selects_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """async_set_temperature picks the degC/degF command from the unit."""
    shadow = RecordingShadow()
    monkeypatch.setattr("delonghi_comfort.client.ShadowConnection", lambda **_: shadow)
    client = await _logged_in_client()
    await client.async_connect("THING")

    await client.async_set_temperature(22)  # defaults to Celsius
    await client.async_set_temperature(72, unit=TemperatureUnit.FAHRENHEIT)

    assert shadow.commands == [
        ("SetRoomTempRequest_degC", 22),
        ("SetRoomTempRequest_degF", 72),
    ]


async def test_set_timezone_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """async_set_timezone sends SetTMZoneRequest with the identifier as-is."""
    shadow = RecordingShadow()
    monkeypatch.setattr("delonghi_comfort.client.ShadowConnection", lambda **_: shadow)
    client = await _logged_in_client()
    await client.async_connect("THING")

    await client.async_set_timezone("Europe/London")

    assert shadow.commands == [("SetTMZoneRequest", "Europe/London")]


async def test_refresh_jwt_rotates_live_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refreshing the JWT propagates the new token to the live shadow connection."""
    shadow = RecordingShadow()
    monkeypatch.setattr("delonghi_comfort.client.ShadowConnection", lambda **_: shadow)
    client = await _logged_in_client()
    await client.async_connect("THING")

    await client.async_refresh_jwt()

    assert shadow.jwt == "jwt-token"


async def test_async_command_encodes_typed_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """async_command encodes each command's typed value onto the wire."""
    shadow = RecordingShadow()
    monkeypatch.setattr("delonghi_comfort.client.ShadowConnection", lambda **_: shadow)
    client = await _logged_in_client()
    await client.async_connect("THING")

    await client.async_command(Commands.POWER, True)
    await client.async_command(Commands.BRIGHTNESS, 2)
    await client.async_command(Commands.TEMP_UNIT, TemperatureUnit.FAHRENHEIT)
    await client.async_command(Commands.TMZONE, "Europe/London")

    assert shadow.commands == [
        ("SetDeviceStatusRequest", 1),
        ("SetBrightnessLevelRequest", 2),
        ("SetTempUnitRequest", 1),
        ("SetTMZoneRequest", "Europe/London"),
    ]


async def test_status_and_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_status returns a MachineStatus and listeners receive live updates."""
    shadow = RecordingShadow()
    monkeypatch.setattr("delonghi_comfort.client.ShadowConnection", lambda **_: shadow)
    client = await _logged_in_client()

    seen: list[MachineStatus] = []
    client.add_status_listener(seen.append)
    await client.async_connect("THING")

    status = await client.async_get_status()
    assert status.is_on is True
    assert status.target_temperature == 21

    shadow.fire({"DeviceStatus": 0, "TempSetPoint": 19})
    assert seen[-1].is_on is False
    assert seen[-1].target_temperature == 19


async def test_brightness_out_of_range() -> None:
    """Brightness outside 0-3 raises before any command is sent."""
    session = make_session()
    client = DelonghiComfort(session=session)
    with pytest.raises(ValueError, match="brightness"):
        await client.async_set_brightness(9)


async def test_requires_authentication() -> None:
    """Calling the API before login raises AuthenticationError."""
    session = make_session()
    client = DelonghiComfort(session=session)
    with pytest.raises(AuthenticationError):
        await client.async_get_devices()
