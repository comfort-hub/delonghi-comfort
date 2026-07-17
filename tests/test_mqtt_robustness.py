"""Robustness tests for the MQTT transport.

Listener isolation, reconnect supervision, shadow-rejection handling, publish
failures and future cleanup — the hardening in the "MQTT transport robustness"
change (library issues #2-#8).
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, Self, cast

import aiomqtt
import pytest

from delonghi_comfort import mqtt
from delonghi_comfort.const import SHADOW_STATUS, command_response_topic, shadow_topic
from delonghi_comfort.exceptions import (
    CommandTimeoutError,
    DelonghiComfortError,
    TransportError,
)
from delonghi_comfort.mqtt import ShadowConnection

from .fakes import FakeMqttClient

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

THING = "EUPDL01COM000000004875"


def _conn() -> ShadowConnection:
    return ShadowConnection(thing_name=THING, jwt="jwt", endpoint="broker")


def _future() -> asyncio.Future[dict[str, Any]]:
    return asyncio.get_running_loop().create_future()


# -- #2: a raising listener must not kill the supervisor ----------------------
async def test_notify_survives_a_raising_listener() -> None:
    """One listener raising does not stop others or propagate out of dispatch."""
    conn = _conn()
    seen: list[dict[str, Any]] = []

    def boom(_snapshot: dict[str, Any]) -> None:
        raise RuntimeError("consumer bug")

    conn.add_listener(boom)
    conn.add_listener(seen.append)

    # Dispatching a status update invokes both listeners; must not raise.
    conn._dispatch(
        shadow_topic(THING, SHADOW_STATUS, "get/accepted"),
        json.dumps({"state": {"reported": {"DeviceStatus": 1}}}),
    )

    assert seen
    assert seen[-1]["DeviceStatus"] == 1


# -- #4: get/rejected must fail the waiter promptly ---------------------------
async def test_dispatch_rejects_pending_get_waiter() -> None:
    """A shadow get/rejected fails the pending getter instead of dropping it."""
    conn = _conn()
    fut = _future()
    conn._get_waiters.setdefault(SHADOW_STATUS, []).append(fut)

    conn._dispatch(
        shadow_topic(THING, SHADOW_STATUS, "get/rejected"),
        json.dumps({"code": 404, "message": "No shadow exists"}),
    )

    assert fut.done()
    with pytest.raises(DelonghiComfortError):
        fut.result()
    assert conn._get_waiters.get(SHADOW_STATUS, []) == []


async def test_get_shadow_raises_promptly_on_rejection() -> None:
    """async_get_shadow surfaces a rejection without waiting for the timeout."""
    conn = _conn()
    client = FakeMqttClient()
    conn._client = cast("aiomqtt.Client", client)
    conn._connected.set()

    task = asyncio.create_task(conn.async_get_shadow(SHADOW_STATUS))
    for _ in range(50):
        if client.published:
            break
        await asyncio.sleep(0)

    conn._dispatch(
        shadow_topic(THING, SHADOW_STATUS, "get/rejected"),
        json.dumps({"code": 404, "message": "No shadow exists"}),
    )
    with pytest.raises(DelonghiComfortError):
        await asyncio.wait_for(task, timeout=1.0)


# -- #5: publish failure wraps and cleans up ----------------------------------
class _RaisingPublishClient(FakeMqttClient):
    async def publish(self, topic: str, payload: Any = None, qos: int = 0) -> None:
        raise aiomqtt.MqttError("socket closed")


async def test_send_command_publish_failure_wraps_and_cleans() -> None:
    """A publish MqttError becomes TransportError and leaks no pending future."""
    conn = _conn()
    conn._client = cast("aiomqtt.Client", _RaisingPublishClient())
    conn._connected.set()

    with pytest.raises(TransportError):
        await conn.async_send_command("SetDeviceStatusRequest", 1)
    assert conn._pending == {}


async def test_get_shadow_publish_failure_wraps_and_cleans() -> None:
    """A publish MqttError in async_get_shadow wraps and leaks no waiter."""
    conn = _conn()
    conn._client = cast("aiomqtt.Client", _RaisingPublishClient())
    conn._connected.set()

    with pytest.raises(TransportError):
        await conn.async_get_shadow(SHADOW_STATUS)
    assert conn._get_waiters.get(SHADOW_STATUS, []) == []


# -- #7: get waiter must not leak on timeout ----------------------------------
async def test_get_shadow_timeout_removes_waiter(monkeypatch: pytest.MonkeyPatch) -> None:
    """A timed-out get removes its waiter from _get_waiters."""
    monkeypatch.setattr(mqtt, "STATUS_TIMEOUT", 0.05)
    conn = _conn()
    conn._client = cast("aiomqtt.Client", FakeMqttClient())
    conn._connected.set()

    with pytest.raises(CommandTimeoutError):
        await conn.async_get_shadow(SHADOW_STATUS)
    assert conn._get_waiters.get(SHADOW_STATUS, []) == []


# -- #8: RequestId collision must not orphan an in-flight command -------------
async def test_send_command_regenerates_on_requestid_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A colliding RequestId is regenerated; the existing future is untouched."""
    conn = _conn()  # created first so its client_id doesn't consume a scripted id
    ids = iter(["AAAAA", "BBBBB"])
    monkeypatch.setattr(mqtt, "generate_request_id", lambda: next(ids))

    client = FakeMqttClient()
    conn._client = cast("aiomqtt.Client", client)
    conn._connected.set()
    existing = _future()
    conn._pending["AAAAA"] = existing

    task = asyncio.create_task(conn.async_send_command("SetDeviceStatusRequest", 1))
    for _ in range(50):
        if client.published:
            break
        await asyncio.sleep(0)

    payload = json.loads(client.published[-1][1])
    assert payload["RequestId"] == "BBBBB"
    assert conn._pending["AAAAA"] is existing  # not overwritten
    assert "BBBBB" in conn._pending

    conn._dispatch(
        command_response_topic(THING),
        json.dumps({"RequestId": "BBBBB", "Response": "OK"}),
    )
    assert (await task)["Response"] == "OK"
    existing.cancel()


# -- #2/#3/#6: supervisor survives, reconnects, re-subscribes, signals, cleans -
class _ScriptedClient:
    """A fake aiomqtt.Client whose message stream is scripted per connection."""

    instances: list[_ScriptedClient] = []

    def __init__(self, conn: ShadowConnection, msg: Any, **_: Any) -> None:
        self._conn = conn
        self._msg = msg
        self.subscribed: list[str] = []
        self.index = len(_ScriptedClient.instances)
        _ScriptedClient.instances.append(self)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def subscribe(self, topic: str, qos: int = 0) -> None:
        self.subscribed.append(topic)

    async def publish(self, *_a: Any, **_k: Any) -> None:
        return None

    @property
    def messages(self) -> AsyncIterator[Any]:
        return self._gen()

    async def _gen(self) -> AsyncIterator[Any]:
        # Every connection delivers one status update (proves dispatch runs),
        # the second one stops the supervisor, then the link "drops".
        yield self._msg
        if self.index >= 1:
            self._conn._stop = True
        raise aiomqtt.MqttError("connection dropped")


class _Msg:
    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = topic
        self.payload = payload


async def test_run_supervisor_reconnects_survives_and_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reconnect, re-subscribe, survive a bad listener, signal, and clean up.

    The supervisor must survive a raising listener, reconnect and re-subscribe,
    fire the error listener, and fail pending futures when the link drops.
    """
    monkeypatch.setattr(mqtt, "_RECONNECT_DELAY", 0.0)
    _ScriptedClient.instances = []

    conn = _conn()
    good: list[dict[str, Any]] = []
    errors: list[Exception] = []
    conn.add_listener(lambda _s: (_ for _ in ()).throw(RuntimeError("bug")))
    conn.add_listener(good.append)
    conn.add_error_listener(errors.append)

    pending = _future()
    conn._pending["inflight"] = pending

    msg = _Msg(
        shadow_topic(THING, SHADOW_STATUS, "get/accepted"),
        json.dumps({"state": {"reported": {"DeviceStatus": 1}}}).encode(),
    )
    monkeypatch.setattr(
        mqtt.aiomqtt, "Client", lambda **kw: _ScriptedClient(conn, msg, **kw)
    )

    await conn.start()
    await asyncio.wait_for(conn._runner, timeout=3.0)  # type: ignore[arg-type]

    # Reconnected at least once and re-subscribed each time.
    assert len(_ScriptedClient.instances) >= 2
    assert all(c.subscribed for c in _ScriptedClient.instances)
    # Survived the raising listener; the good one still saw updates.
    assert len(good) >= 2
    # The connection error was surfaced to the error listener.
    assert errors
    assert isinstance(errors[0], aiomqtt.MqttError)
    # In-flight future was failed on the drop.
    assert pending.done()
    with pytest.raises(TransportError):
        pending.result()
