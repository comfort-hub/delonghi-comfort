"""Async Python client for De'Longhi 'My Comfort Hub' (Daedalus) connected heaters."""

from __future__ import annotations

from .client import DelonghiComfort
from .const import Command
from .exceptions import (
    AuthenticationError,
    CommandError,
    CommandTimeoutError,
    DelonghiComfortError,
    TransportError,
)
from .gigya import GigyaCredentials
from .models import Device, MachineCapabilities, MachineStatus

__all__ = [
    "AuthenticationError",
    "Command",
    "CommandError",
    "CommandTimeoutError",
    "DelonghiComfort",
    "DelonghiComfortError",
    "Device",
    "GigyaCredentials",
    "MachineCapabilities",
    "MachineStatus",
    "TransportError",
]
