"""REST calls against the De'Longhi AWS API Gateway.

Only ``GET devices`` is needed and it is authorized by the Gigya JWT as a Bearer token
(a Lambda authorizer), not SigV4. The endpoint is intermittently flaky (transient
403/5xx), so the request is retried a few times before the failure is surfaced.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import REST_BASE_URLS, SOURCE
from .exceptions import AuthenticationError, DelonghiComfortError, TransportError
from .models import Device

# The devices endpoint intermittently returns transient 403/5xx. Retry a few times
# with a short, growing backoff before giving up, so a flaky-cloud blip does not
# surface as an error to the caller.
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 0.5


async def async_get_devices(
    session: aiohttp.ClientSession,
    jwt: str,
    region: str = "eu",
    *,
    retries: int = _RETRY_ATTEMPTS,
) -> list[Device]:
    """Return the appliances owned by / shared with the authenticated account.

    Retries transient cloud failures with a short backoff; the last failure is
    raised once the retry budget is exhausted. Pass ``retries=1`` to fail fast
    (e.g. during region discovery, where a rejected region should move on, not
    linger on retries).
    """
    last_exc: DelonghiComfortError = TransportError("devices request not attempted")
    for attempt in range(retries):
        try:
            return await _async_get_devices_once(session, jwt, region)
        except DelonghiComfortError as exc:
            last_exc = exc
            if attempt + 1 < retries:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
    raise last_exc


async def _async_get_devices_once(
    session: aiohttp.ClientSession, jwt: str, region: str
) -> list[Device]:
    """Perform a single ``GET devices`` request."""
    url = f"{REST_BASE_URLS[region]}devices"
    headers = {
        "Authorization": f"Bearer {jwt}",
        "source": SOURCE,
        "Accept": "application/json",
    }
    try:
        async with session.get(url, headers=headers) as response:
            if response.status in (401, 403):
                raise AuthenticationError(
                    f"devices request unauthorized (HTTP {response.status})"
                )
            if response.status != 200:
                body = await response.text()
                raise TransportError(
                    f"devices request failed (HTTP {response.status}): {body[:200]}"
                )
            data: dict[str, Any] = await response.json(content_type=None)
    except aiohttp.ClientError as exc:
        raise TransportError(f"devices request failed: {exc}") from exc

    entries = [*data.get("ownedByMe", []), *data.get("sharedToMe", [])]
    return [Device.from_dict(entry) for entry in entries]
