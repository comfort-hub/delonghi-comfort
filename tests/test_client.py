"""End-to-end tests for the DelonghiComfort client with fake transports."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from delonghi_comfort import Commands, ConnectionState, TemperatureUnit
from delonghi_comfort.client import DelonghiComfort
from delonghi_comfort.exceptions import AuthenticationError, TransportError

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


async def test_error_listener_observes_connection_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Observe live-connection failures through an error listener.

    Failures (e.g. an expired-JWT reconnect) reach the listener instead of
    looping silently; removing the listener stops delivery.
    """
    shadow = RecordingShadow()
    monkeypatch.setattr("delonghi_comfort.client.ShadowConnection", lambda **_: shadow)
    client = await _logged_in_client()
    seen: list[Exception] = []
    remove = client.add_error_listener(seen.append)
    await client.async_connect("THING")

    shadow.fire_error(TransportError("connection lost"))
    assert [type(err) for err in seen] == [TransportError]

    remove()
    shadow.fire_error(TransportError("again"))
    assert len(seen) == 1


async def test_connection_listener_tracks_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A connection listener sees state changes and is_connected reflects them."""
    shadow = RecordingShadow()
    monkeypatch.setattr("delonghi_comfort.client.ShadowConnection", lambda **_: shadow)
    client = await _logged_in_client()
    seen: list[ConnectionState] = []
    client.add_connection_listener(seen.append)

    before = client.is_connected
    await client.async_connect("THING")
    shadow.fire_connection(ConnectionState.CONNECTED)
    while_connected = client.is_connected
    shadow.fire_connection(ConnectionState.DISCONNECTED)
    while_disconnected = client.is_connected

    assert (before, while_connected, while_disconnected) == (False, True, False)
    assert seen == [ConnectionState.CONNECTED, ConnectionState.DISCONNECTED]


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


async def test_status_carries_reported_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Polled and pushed statuses carry the shadow's report-time metadata."""
    shadow = RecordingShadow()
    shadow.reported_metadata = {"RoomTemp": {"timestamp": 1_700_000_000}}
    monkeypatch.setattr("delonghi_comfort.client.ShadowConnection", lambda **_: shadow)
    client = await _logged_in_client()
    seen: list[MachineStatus] = []
    client.add_status_listener(seen.append)
    await client.async_connect("THING")

    expected = datetime.fromtimestamp(1_700_000_000, tz=UTC)
    status = await client.async_get_status()
    assert status.last_reported_at == expected

    shadow.fire({"DeviceStatus": 0})
    assert seen[-1].last_reported_at == expected


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
