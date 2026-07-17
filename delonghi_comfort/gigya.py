"""Gigya (SAP CDC) authentication: login and JWT retrieval.

Login uses ``targetEnv=mobile`` + ``sessionExpiration=-1`` to obtain a long-lived
session (token + secret). ``accounts.getJWT`` must be OAuth1-signed with the session
secret, otherwise Gigya returns ``403005`` ("Session not found").
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import secrets
import time
from typing import Any
from urllib.parse import quote, urlencode

import aiohttp

from .const import GIGYA_API_KEYS, GIGYA_BASE_URL, JWT_EXPIRATION_SECONDS
from .exceptions import AuthenticationError, TransportError

# Gigya errorCode returned when an account is not on the probed pool.
_WRONG_POOL_CODE = 400093

# Transient throttle errorCodes: retryable, and NOT a bad-credential signal.
_RATE_LIMIT_CODES = frozenset({403048, 403120})


@dataclass(frozen=True, slots=True)
class GigyaCredentials:
    """A long-lived Gigya session, enough to mint fresh JWTs without a password."""

    api_key: str
    session_token: str
    session_secret: str


def _sign(method: str, url: str, params: dict[str, str], session_secret: str) -> str:
    """Return the Gigya OAuth1 HMAC-SHA1 base64 signature for ``params``."""
    normalized = "&".join(
        f"{quote(key, safe='')}={quote(str(value), safe='')}"
        for key, value in sorted(params.items())
    )
    base = "&".join([method.upper(), quote(url, safe=""), quote(normalized, safe="")])
    digest = hmac.new(
        base64.b64decode(session_secret), base.encode(), hashlib.sha1
    ).digest()
    return base64.b64encode(digest).decode()


class GigyaAuth:
    """Thin async wrapper over the two Gigya endpoints this library needs."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Store the shared aiohttp session used for Gigya calls."""
        self._session = session

    async def _post(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = f"{GIGYA_BASE_URL}{path}"
        try:
            async with self._session.post(
                url,
                data=urlencode(params).encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                status = response.status
                try:
                    payload: dict[str, Any] = await response.json(content_type=None)
                except ValueError as exc:
                    body = await response.text()
                    raise TransportError(
                        f"Gigya {path} returned a non-JSON response "
                        f"(HTTP {status}): {body[:200]}"
                    ) from exc
        except aiohttp.ClientError as exc:
            raise TransportError(f"Gigya request to {path} failed: {exc}") from exc
        return payload

    async def login(self, email: str, password: str) -> GigyaCredentials:
        """Log in, auto-probing the account pools, and return session credentials."""
        last_error: str | None = None
        for pool, api_key in GIGYA_API_KEYS.items():
            payload = await self._post(
                "/accounts.login",
                {
                    "loginID": email,
                    "password": password,
                    "apiKey": api_key,
                    "targetEnv": "mobile",
                    "sessionExpiration": "-1",
                },
            )
            error_code = payload.get("errorCode", 0)
            if error_code == 0:
                session = payload.get("sessionInfo", {})
                token = session.get("sessionToken")
                secret = session.get("sessionSecret")
                if token and secret:
                    return GigyaCredentials(
                        api_key=api_key, session_token=token, session_secret=secret
                    )
                last_error = "login succeeded but session was empty"
            elif error_code == _WRONG_POOL_CODE:
                last_error = f"pool {pool}: wrong pool"
                continue
            elif error_code in _RATE_LIMIT_CODES:
                # Transient throttle: retryable, and not a credential problem.
                raise TransportError(
                    f"Gigya rate-limited login (error {error_code}): "
                    f"{payload.get('errorMessage', 'try again later')}"
                )
            else:
                # A definite credential error (e.g. bad password): stop probing.
                raise AuthenticationError(
                    f"Gigya error {error_code}: {payload.get('errorMessage', 'unknown')}"
                )
        raise AuthenticationError(f"login failed for all pools ({last_error})")

    async def get_jwt(self, credentials: GigyaCredentials) -> str:
        """Mint a fresh signed JWT from stored session credentials."""
        url = f"{GIGYA_BASE_URL}/accounts.getJWT"
        params = {
            "apiKey": credentials.api_key,
            "oauth_token": credentials.session_token,
            "expiration": str(JWT_EXPIRATION_SECONDS),
            "timestamp": str(int(time.time())),
            "nonce": secrets.token_hex(16),
        }
        params["sig"] = _sign("POST", url, params, credentials.session_secret)
        payload = await self._post("/accounts.getJWT", params)
        token = payload.get("id_token")
        if not isinstance(token, str) or not token:
            raise AuthenticationError(
                f"getJWT failed: {payload.get('errorMessage', payload)}"
            )
        return token
