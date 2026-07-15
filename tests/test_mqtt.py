"""Tests for the MQTT shadow/command transport correlation logic."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, cast

import pytest

from delonghi_comfort.const import SHADOW_STATUS, command_response_topic, shadow_topic
from delonghi_comfort.exceptions import CommandError
from delonghi_comfort.mqtt import (
    ShadowConnection,
    build_command_payload,
    generate_request_id,
)

from .fakes import FakeMqttClient

if TYPE_CHECKING:
    import aiomqtt

THING = "EUPDL01COM000000004875"


def _conn() -> ShadowConnection:
    return ShadowConnection(thing_name=THING, jwt="jwt", endpoint="broker")


def test_request_id_format() -> None:
    """The request id is 5 alphanumeric characters."""
    rid = generate_request_id()
    assert len(rid) == 5
    assert rid.isalnum()


def test_build_command_payload() -> None:
    """The command envelope matches the app's format."""
    payload = build_command_payload("SetDeviceStatusRequest", 1)
    assert payload["Message"] == "SetDeviceStatusRequest"
    assert payload["AppId"] == "Comfort"
    assert payload["Value"] == 1
    assert len(payload["RequestId"]) == 5


async def test_dispatch_resolves_command_future() -> None:
    """A command/response with a matching RequestId resolves the pending future."""
    conn = _conn()
    future: asyncio.Future[dict[str, object]] = (
        asyncio.get_running_loop().create_future()
    )
    conn._pending["rid1"] = future
    conn._dispatch(
        command_response_topic(THING),
        json.dumps({"RequestId": "rid1", "Response": "OK"}),
    )
    assert future.result()["Response"] == "OK"


async def test_dispatch_updates_status_and_notifies() -> None:
    """A MachineStatus get/accepted updates reported state and notifies listeners."""
    conn = _conn()
    seen: list[dict[str, object]] = []
    conn.add_listener(seen.append)
    conn._dispatch(
        shadow_topic(THING, SHADOW_STATUS, "get/accepted"),
        json.dumps({"state": {"reported": {"DeviceStatus": 1, "TempSetPoint": 22}}}),
    )
    assert conn.reported["DeviceStatus"] == 1
    assert seen
    assert seen[-1]["TempSetPoint"] == 22


async def test_dispatch_merges_update_documents() -> None:
    """update/documents merges only changed fields into reported state."""
    conn = _conn()
    conn._dispatch(
        shadow_topic(THING, SHADOW_STATUS, "get/accepted"),
        json.dumps({"state": {"reported": {"DeviceStatus": 0, "TempSetPoint": 22}}}),
    )
    conn._dispatch(
        shadow_topic(THING, SHADOW_STATUS, "update/documents"),
        json.dumps({"current": {"state": {"reported": {"DeviceStatus": 1}}}}),
    )
    assert conn.reported["DeviceStatus"] == 1
    assert conn.reported["TempSetPoint"] == 22  # preserved


async def test_send_command_awaits_ok_response() -> None:
    """async_send_command publishes and resolves when an OK reply arrives."""
    conn = _conn()
    client = FakeMqttClient()
    conn._client = cast("aiomqtt.Client", client)
    conn._connected.set()

    task = asyncio.create_task(conn.async_send_command("SetDeviceStatusRequest", 1))
    for _ in range(50):
        if client.published:
            break
        await asyncio.sleep(0)

    _topic, payload = client.published[-1]
    request_id = json.loads(payload)["RequestId"]
    conn._dispatch(
        command_response_topic(THING),
        json.dumps(
            {
                "Message": "SetDeviceStatusRequest",
                "Response": "OK",
                "RequestId": request_id,
            }
        ),
    )
    result = await task
    assert result["Response"] == "OK"


async def test_send_command_raises_on_rejection() -> None:
    """A non-OK response raises CommandError."""
    conn = _conn()
    client = FakeMqttClient()
    conn._client = cast("aiomqtt.Client", client)
    conn._connected.set()

    task = asyncio.create_task(conn.async_send_command("SetDeviceStatusRequest", 1))
    for _ in range(50):
        if client.published:
            break
        await asyncio.sleep(0)
    request_id = json.loads(client.published[-1][1])["RequestId"]
    conn._dispatch(
        command_response_topic(THING),
        json.dumps({"Response": "FAIL", "RequestId": request_id}),
    )
    with pytest.raises(CommandError):
        await task
