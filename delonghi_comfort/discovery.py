"""Account-wide device discovery across all supported regions."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from .const import SUPPORTED_REGIONS
from .exceptions import DelonghiComfortError, TransportError
from .gigya import GigyaAuth
from .rest import async_get_devices

if TYPE_CHECKING:
    import aiohttp

    from .gigya import GigyaCredentials
    from .models import Device

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DiscoveredDevice:
    """A device found during discovery, tagged with the region that hosts it."""

    device: Device
    region: str


async def async_discover(
    session: aiohttp.ClientSession, email: str, password: str
) -> tuple[GigyaCredentials, list[DiscoveredDevice]]:
    """Log in once and return every device on the account across all regions.

    A single Gigya login (which itself probes every account pool) and a single
    JWT are enough to enumerate every region: the JWT is the account's global
    identity and is accepted by each regional device endpoint.

    Args:
        session: Shared aiohttp session.
        email: Account email address.
        password: Account password.

    Returns:
        The Gigya session credentials and every discovered device, each tagged
        with the region whose backend hosts it.

    Raises:
        AuthenticationError: The credentials were rejected at login, or no region
            answered and none failed transiently (every region rejected the JWT).
        TransportError: No region answered and at least one failed transiently,
            so discovery could not be completed.

    """
    gigya = GigyaAuth(session)
    credentials = await gigya.login(email, password)
    jwt = await gigya.get_jwt(credentials)
    found: list[DiscoveredDevice] = []
    errors: list[DelonghiComfortError] = []
    for region in SUPPORTED_REGIONS:
        try:
            # Fail fast per region: a rejected region should move on to the next,
            # not spend the transient-retry budget.
            devices = await async_get_devices(session, jwt, region, retries=1)
        except DelonghiComfortError as err:
            _LOGGER.debug("discovery: skipping region %s: %s", region, err)
            errors.append(err)
            continue
        found.extend(
            DiscoveredDevice(device=device, region=region) for device in devices
        )
    if not found and errors:
        raise next((e for e in errors if isinstance(e, TransportError)), errors[-1])
    return credentials, found
