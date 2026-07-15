"""Tests for the REST device listing."""

from __future__ import annotations

import pytest

from delonghi_comfort.exceptions import AuthenticationError, TransportError
from delonghi_comfort.rest import async_get_devices

from .fakes import FakeResponse, make_session


async def test_get_devices() -> None:
    """Owned and shared devices are parsed into Device objects."""
    session = make_session(
        {
            "devices": FakeResponse(
                json_data={
                    "ownedByMe": [{"machineName": "THING", "status": "ONLINE"}],
                    "sharedToMe": [],
                }
            )
        }
    )
    devices = await async_get_devices(session, "jwt")
    assert len(devices) == 1
    assert devices[0].thing_name == "THING"
    assert devices[0].online is True


async def test_get_devices_unauthorized() -> None:
    """401/403 raises AuthenticationError."""
    session = make_session({"devices": FakeResponse(status=403)})
    with pytest.raises(AuthenticationError):
        await async_get_devices(session, "jwt")


async def test_get_devices_server_error() -> None:
    """A non-200 raises TransportError."""
    session = make_session({"devices": FakeResponse(status=500, text_data="boom")})
    with pytest.raises(TransportError):
        await async_get_devices(session, "jwt")
