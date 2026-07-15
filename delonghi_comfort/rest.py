"""REST calls against the De'Longhi AWS API Gateway.

Only ``GET devices`` is needed and it is authorized by the Gigya JWT as a Bearer token
(a Lambda authorizer), not SigV4.
"""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import REST_BASE_URLS, SOURCE
from .exceptions import AuthenticationError, TransportError
from .models import Device


async def async_get_devices(
    session: aiohttp.ClientSession, jwt: str, region: str = "eu"
) -> list[Device]:
    """Return the appliances owned by / shared with the authenticated account."""
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
