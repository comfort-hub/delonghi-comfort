"""AWS IoT MQTT transport: read named shadows and send control commands.

Reading is done via the standard shadow ``get``/``update`` topics; control is done by
publishing to ``<thing>/commands/request`` and correlating the reply on
``<thing>/commands/response`` by ``RequestId``. The connection is supervised: it
reconnects automatically and re-subscribes.

NOTE: the MQTT client-id must NOT equal the thing name — the physical heater connects
as ``client-id == thingName`` and AWS IoT evicts the older session on a duplicate id.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
import json
import logging
import secrets
import ssl
import string
from typing import Any

import aiomqtt

from .const import (
    APP_ID,
    COMMAND_TIMEOUT,
    IOT_AUTHORIZER,
    IOT_PORT,
    SHADOW_CAPABILITIES,
    SHADOW_STATUS,
    STATUS_TIMEOUT,
    command_request_topic,
    command_response_topic,
    shadow_topic,
)
from .exceptions import CommandError, CommandTimeoutError, TransportError

_LOGGER = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 20.0
_RECONNECT_DELAY = 5.0
_ID_ALPHABET = string.ascii_letters + string.digits

ReportedCallback = Callable[[dict[str, Any]], None]


def generate_request_id() -> str:
    """Return a short random ``RequestId`` (5 chars, matching the app's format)."""
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(5))


def build_command_payload(message: str, value: int | str) -> dict[str, Any]:
    """Build the JSON body published to the command/request topic.

    ``value`` is usually an ``int`` but may be a ``str`` for commands that carry
    an encoded payload (e.g. a base64 schedule blob).
    """
    return {
        "Message": message,
        "AppId": APP_ID,
        "Value": value,
        "RequestId": generate_request_id(),
    }


def alpn_mqtt_context() -> ssl.SSLContext:
    """Return a default TLS context negotiating the AWS IoT ``mqtt`` ALPN protocol."""
    context = ssl.create_default_context()
    context.set_alpn_protocols(["mqtt"])
    return context


class ShadowConnection:
    """A supervised MQTT connection to one thing's shadows + command channel."""

    def __init__(
        self,
        *,
        thing_name: str,
        jwt: str,
        endpoint: str,
        tls_context: ssl.SSLContext | None = None,
    ) -> None:
        """Configure (but do not open) the connection for ``thing_name``."""
        self._thing = thing_name
        self._jwt = jwt
        self._endpoint = endpoint
        self._tls = tls_context or alpn_mqtt_context()
        self._client_id = f"{thing_name}-{generate_request_id()}"
        self._client: aiomqtt.Client | None = None
        self._runner: asyncio.Task[None] | None = None
        self._connected = asyncio.Event()
        self._stop = False
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._get_waiters: dict[str, list[asyncio.Future[dict[str, Any]]]] = {}
        self._listeners: list[ReportedCallback] = []
        self._reported: dict[str, Any] = {}

    @property
    def reported(self) -> dict[str, Any]:
        """The most recent merged ``MachineStatus`` reported state."""
        return dict(self._reported)

    def update_jwt(self, jwt: str) -> None:
        """Replace the JWT used on the next (re)connect."""
        self._jwt = jwt

    def add_listener(self, callback: ReportedCallback) -> Callable[[], None]:
        """Register a callback invoked with the merged reported state on every change."""
        self._listeners.append(callback)

        def _remove() -> None:
            with suppress(ValueError):
                self._listeners.remove(callback)

        return _remove

    async def start(self) -> None:
        """Open the connection and wait until the first successful connect."""
        self._stop = False
        self._runner = asyncio.create_task(self._run())
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=_CONNECT_TIMEOUT)
        except TimeoutError as exc:
            await self.stop()
            raise TransportError("timed out connecting to the AWS IoT broker") from exc

    async def stop(self) -> None:
        """Close the connection and stop the supervisor."""
        self._stop = True
        if self._runner is not None:
            self._runner.cancel()
            with suppress(asyncio.CancelledError):
                await self._runner
            self._runner = None
        self._fail_pending(TransportError("connection closed"))

    async def _run(self) -> None:
        while not self._stop:
            try:
                async with aiomqtt.Client(
                    hostname=self._endpoint,
                    port=IOT_PORT,
                    username=f"?x-amz-customauthorizer-name={IOT_AUTHORIZER}",
                    password=self._jwt,
                    identifier=self._client_id,
                    tls_context=self._tls,
                    protocol=aiomqtt.ProtocolVersion.V5,
                    keepalive=30,
                ) as client:
                    self._client = client
                    await self._subscribe(client)
                    self._connected.set()
                    async for message in client.messages:
                        self._dispatch(str(message.topic), message.payload)
            except aiomqtt.MqttError as exc:
                _LOGGER.debug("MQTT connection to %s lost: %s", self._endpoint, exc)
            finally:
                self._connected.clear()
                self._client = None
            if not self._stop:
                await asyncio.sleep(_RECONNECT_DELAY)

    async def _subscribe(self, client: aiomqtt.Client) -> None:
        topics = [
            shadow_topic(self._thing, SHADOW_STATUS, "get/accepted"),
            shadow_topic(self._thing, SHADOW_STATUS, "get/rejected"),
            shadow_topic(self._thing, SHADOW_STATUS, "update/documents"),
            shadow_topic(self._thing, SHADOW_STATUS, "update/accepted"),
            shadow_topic(self._thing, SHADOW_CAPABILITIES, "get/accepted"),
            command_response_topic(self._thing),
        ]
        for topic in topics:
            await client.subscribe(topic, qos=1)

    def _dispatch(self, topic: str, raw: Any) -> None:
        """Route one received message to the right waiter/listener (pure, testable)."""
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return
        if not isinstance(payload, dict):
            return

        if topic == command_response_topic(self._thing):
            request_id = payload.get("RequestId")
            future = self._pending.pop(request_id, None) if request_id else None
            if future is not None and not future.done():
                future.set_result(payload)
            return

        if topic.endswith("get/accepted"):
            shadow = topic.split("/shadow/name/", 1)[-1].split("/", 1)[0]
            reported = payload.get("state", {}).get("reported", {})
            self._resolve_get(shadow, reported)
            if shadow == SHADOW_STATUS:
                self._reported = dict(reported)
                self._notify()
            return

        if topic.endswith(f"{SHADOW_STATUS}/update/documents"):
            reported = payload.get("current", {}).get("state", {}).get("reported", {})
            if reported:
                self._reported.update(reported)
                self._notify()

    def _resolve_get(self, shadow: str, reported: dict[str, Any]) -> None:
        for future in self._get_waiters.pop(shadow, []):
            if not future.done():
                future.set_result(reported)

    def _notify(self) -> None:
        snapshot = dict(self._reported)
        for listener in list(self._listeners):
            listener(snapshot)

    def _fail_pending(self, error: Exception) -> None:
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(error)
        self._pending.clear()
        for waiters in self._get_waiters.values():
            for future in waiters:
                if not future.done():
                    future.set_exception(error)
        self._get_waiters.clear()

    async def _ensure_client(self) -> aiomqtt.Client:
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=_CONNECT_TIMEOUT)
        except TimeoutError as exc:
            raise TransportError("not connected to the AWS IoT broker") from exc
        if self._client is None:  # pragma: no cover - guarded by the event
            raise TransportError("not connected to the AWS IoT broker")
        return self._client

    async def async_get_shadow(self, shadow: str = SHADOW_STATUS) -> dict[str, Any]:
        """Request and return the current ``reported`` state of a named shadow."""
        client = await self._ensure_client()
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._get_waiters.setdefault(shadow, []).append(future)
        await client.publish(
            shadow_topic(self._thing, shadow, "get"), payload=b"", qos=1
        )
        try:
            return await asyncio.wait_for(future, timeout=STATUS_TIMEOUT)
        except TimeoutError as exc:
            raise CommandTimeoutError(
                f"no response getting the {shadow} shadow"
            ) from exc

    async def async_send_command(
        self, message: str, value: int | str
    ) -> dict[str, Any]:
        """Publish a command and await the device's ``Response: OK`` acknowledgement."""
        client = await self._ensure_client()
        payload = build_command_payload(message, value)
        request_id: str = payload["RequestId"]
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[request_id] = future
        await client.publish(
            command_request_topic(self._thing), payload=json.dumps(payload), qos=1
        )
        try:
            response = await asyncio.wait_for(future, timeout=COMMAND_TIMEOUT)
        except TimeoutError as exc:
            self._pending.pop(request_id, None)
            raise CommandTimeoutError(f"no ack for command {message}") from exc
        if response.get("Response") != "OK":
            raise CommandError(
                f"command {message} rejected: {response.get('Response')}"
            )
        return response
