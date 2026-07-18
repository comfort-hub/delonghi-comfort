"""Tests for cross-region device discovery."""

from __future__ import annotations

import base64

import pytest

from delonghi_comfort import DiscoveredDevice, async_discover
from delonghi_comfort.exceptions import AuthenticationError, TransportError

from .fakes import FakeResponse, make_session

_SECRET = base64.b64encode(b"secret").decode()


def _gigya_routes() -> dict[str, FakeResponse]:
    return {
        "accounts.login": FakeResponse(
            json_data={
                "errorCode": 0,
                "sessionInfo": {"sessionToken": "st", "sessionSecret": _SECRET},
            }
        ),
        "accounts.getJWT": FakeResponse(json_data={"id_token": "jwt"}),
    }


def _devices(*names: str) -> FakeResponse:
    return FakeResponse(
        json_data={"ownedByMe": [{"machineName": n, "status": "ONLINE"} for n in names]}
    )


async def test_discover_eu_only() -> None:
    """A device only in eu is returned tagged with region eu."""
    session = make_session(
        {**_gigya_routes(), "eu-central-1": _devices("EU1"), "us-east-1": _devices()}
    )
    credentials, found = await async_discover(session, "me@example.com", "pw")
    assert credentials.session_token == "st"
    assert [(d.device.thing_name, d.region) for d in found] == [("EU1", "eu")]
    assert isinstance(found[0], DiscoveredDevice)


async def test_discover_us_only() -> None:
    """A device only in us is returned tagged with region us."""
    session = make_session(
        {**_gigya_routes(), "eu-central-1": _devices(), "us-east-1": _devices("US1")}
    )
    _, found = await async_discover(session, "me@example.com", "pw")
    assert [(d.device.thing_name, d.region) for d in found] == [("US1", "us")]


async def test_discover_aggregates_both_regions() -> None:
    """Devices in both regions are aggregated, each tagged correctly."""
    session = make_session(
        {
            **_gigya_routes(),
            "eu-central-1": _devices("EU1"),
            "us-east-1": _devices("US1"),
        }
    )
    _, found = await async_discover(session, "me@example.com", "pw")
    # Ordered: eu is probed before us, so its devices come first.
    assert [(d.device.thing_name, d.region) for d in found] == [
        ("EU1", "eu"),
        ("US1", "us"),
    ]


async def test_discover_none_returns_empty() -> None:
    """No devices anywhere returns credentials and an empty list."""
    session = make_session(
        {**_gigya_routes(), "eu-central-1": _devices(), "us-east-1": _devices()}
    )
    credentials, found = await async_discover(session, "me@example.com", "pw")
    assert credentials.session_token == "st"
    assert found == []


async def test_discover_bad_password_raises_auth() -> None:
    """A rejected login propagates AuthenticationError."""
    session = make_session(
        {"accounts.login": FakeResponse(json_data={"errorCode": 403042})}
    )
    with pytest.raises(AuthenticationError):
        await async_discover(session, "me@example.com", "wrong")


async def test_discover_region_auth_rejection_raises() -> None:
    """A region rejecting the JWT (401/403) propagates AuthenticationError."""
    session = make_session(
        {
            **_gigya_routes(),
            "eu-central-1": _devices("EU1"),
            "us-east-1": FakeResponse(status=403, text_data="forbidden"),
        }
    )
    with pytest.raises(AuthenticationError):
        await async_discover(session, "me@example.com", "pw")


async def test_discover_one_region_errors_other_empty_raises() -> None:
    """A transient region error with no devices anywhere surfaces the error."""
    session = make_session(
        {
            **_gigya_routes(),
            "eu-central-1": FakeResponse(status=502, text_data="bad gateway"),
            "us-east-1": _devices(),
        }
    )
    with pytest.raises(TransportError):
        await async_discover(session, "me@example.com", "pw")


async def test_discover_skips_a_transient_region() -> None:
    """A region that errors transiently is skipped when another has devices."""
    session = make_session(
        {
            **_gigya_routes(),
            "eu-central-1": FakeResponse(status=502, text_data="bad gateway"),
            "us-east-1": _devices("US1"),
        }
    )
    _, found = await async_discover(session, "me@example.com", "pw")
    assert [(d.device.thing_name, d.region) for d in found] == [("US1", "us")]


async def test_discover_all_regions_failing_raises() -> None:
    """If every region errors and none have devices, the error is raised."""
    session = make_session(
        {
            **_gigya_routes(),
            "eu-central-1": FakeResponse(status=502, text_data="bad gateway"),
            "us-east-1": FakeResponse(status=503, text_data="unavailable"),
        }
    )
    with pytest.raises(TransportError):
        await async_discover(session, "me@example.com", "pw")
