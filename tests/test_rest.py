"""Tests for the REST device listing."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from delonghi_comfort import rest
from delonghi_comfort.exceptions import AuthenticationError, TransportError
from delonghi_comfort.rest import async_get_devices

from .fakes import FakeResponse, make_session

if TYPE_CHECKING:
    import aiohttp


class _SequenceSession:
    """A ClientSession stand-in returning queued responses in order (last repeats)."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = responses
        self.calls = 0

    def get(self, url: str, headers: dict[str, str] | None = None) -> FakeResponse:
        response = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return response


def _seq(responses: list[FakeResponse]) -> aiohttp.ClientSession:
    return cast("aiohttp.ClientSession", _SequenceSession(responses))


_ONLINE = FakeResponse(
    json_data={
        "ownedByMe": [{"machineName": "THING", "status": "ONLINE"}],
        "sharedToMe": [],
    }
)


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


async def test_get_devices_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    """A persistent 401/403 raises AuthenticationError (after retries)."""
    monkeypatch.setattr(rest, "_RETRY_BACKOFF_SECONDS", 0)
    session = make_session({"devices": FakeResponse(status=403)})
    with pytest.raises(AuthenticationError):
        await async_get_devices(session, "jwt")


async def test_get_devices_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A persistent non-200 raises TransportError (after retries)."""
    monkeypatch.setattr(rest, "_RETRY_BACKOFF_SECONDS", 0)
    session = make_session({"devices": FakeResponse(status=500, text_data="boom")})
    with pytest.raises(TransportError):
        await async_get_devices(session, "jwt")


async def test_get_devices_retries_transient_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient 5xx/403 is retried and the next success is returned."""
    monkeypatch.setattr(rest, "_RETRY_BACKOFF_SECONDS", 0)
    session = _seq([FakeResponse(status=500, text_data="boom"), _ONLINE])
    devices = await async_get_devices(session, "jwt")
    assert len(devices) == 1
    assert cast("_SequenceSession", session).calls == 2  # one retry


async def test_get_devices_gives_up_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistent failures raise after exhausting the retry budget."""
    monkeypatch.setattr(rest, "_RETRY_BACKOFF_SECONDS", 0)
    session = _seq([FakeResponse(status=500, text_data="boom")])
    with pytest.raises(TransportError):
        await async_get_devices(session, "jwt")
    assert cast("_SequenceSession", session).calls == rest._RETRY_ATTEMPTS
