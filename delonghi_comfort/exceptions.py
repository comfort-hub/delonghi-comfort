"""Exceptions raised by the De'Longhi Comfort client."""

from __future__ import annotations


class DelonghiComfortError(Exception):
    """Base class for all errors raised by this library."""


class AuthenticationError(DelonghiComfortError):
    """Gigya login or JWT retrieval failed (bad credentials or wrong pool)."""


class TransportError(DelonghiComfortError):
    """A transport-level failure talking to the REST API or the MQTT broker."""


class CommandError(DelonghiComfortError):
    """The device rejected a command or did not acknowledge it in time."""


class CommandTimeoutError(CommandError):
    """No response was received on the command/response topic in time."""
