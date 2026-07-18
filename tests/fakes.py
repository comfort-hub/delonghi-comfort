"""Lightweight fakes for aiohttp and aiomqtt used across the test suite."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self, cast

if TYPE_CHECKING:
    import aiohttp


class FakeResponse:
    """Minimal stand-in for an aiohttp response used as an async context manager."""

    def __init__(
        self, status: int = 200, json_data: Any = None, text_data: str = ""
    ) -> None:
        self.status = status
        self._json = json_data
        self._text = text_data

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def json(self, content_type: str | None = None) -> Any:
        return self._json

    async def text(self) -> str:
        return self._text


class FakeSession:
    """aiohttp.ClientSession stand-in that returns responses matched by URL substring."""

    def __init__(self, routes: dict[str, FakeResponse] | None = None) -> None:
        self.routes = routes or {}
        self.calls: list[tuple[str, str, dict[str, str] | None]] = []

    def _match(
        self, method: str, url: str, headers: dict[str, str] | None
    ) -> FakeResponse:
        self.calls.append((method, url, headers))
        for fragment, response in self.routes.items():
            if fragment in url:
                return response
        return FakeResponse(status=404, text_data="no route")

    def post(
        self,
        url: str,
        data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> FakeResponse:
        return self._match("POST", url, headers)

    def get(self, url: str, headers: dict[str, str] | None = None) -> FakeResponse:
        return self._match("GET", url, headers)


class FakeMqttClient:
    """aiomqtt.Client stand-in that records publishes."""

    def __init__(self) -> None:
        self.published: list[tuple[str, Any]] = []

    async def publish(self, topic: str, payload: Any = None, qos: int = 0) -> None:
        self.published.append((topic, payload))

    async def subscribe(self, topic: str, qos: int = 0) -> None:
        return None


class RecordingShadow:
    """Stand-in for ShadowConnection: records commands and can fire listeners."""

    def __init__(self) -> None:
        self.commands: list[tuple[str, int | str]] = []
        self.jwt: str | None = None
        self._listeners: list[Any] = []

    def update_jwt(self, jwt: str) -> None:
        self.jwt = jwt

    def add_listener(self, callback: Any) -> Any:
        self._listeners.append(callback)
        return lambda: None

    def fire(self, reported: dict[str, Any]) -> None:
        """Simulate the device pushing a reported-state update."""
        for callback in self._listeners:
            callback(reported)

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def async_send_command(
        self, message: str, value: int | str
    ) -> dict[str, Any]:
        self.commands.append((message, value))
        return {"Message": message, "Response": "OK", "Value": value}

    async def async_get_shadow(self, shadow: str = "MachineStatus") -> dict[str, Any]:
        return {"DeviceStatus": 1, "TempSetPoint": 21}


def make_session(
    routes: dict[str, FakeResponse] | None = None,
) -> aiohttp.ClientSession:
    """Return a FakeSession typed as a real aiohttp ClientSession for injection."""
    return cast("aiohttp.ClientSession", FakeSession(routes))


__all__ = [
    "FakeMqttClient",
    "FakeResponse",
    "FakeSession",
    "RecordingShadow",
    "make_session",
]
