"""Tests for Gigya authentication."""

from __future__ import annotations

import base64

import pytest

from delonghi_comfort.exceptions import AuthenticationError
from delonghi_comfort.gigya import GigyaAuth, GigyaCredentials, _sign

from .fakes import FakeResponse, make_session

_SECRET = base64.b64encode(b"a-shared-secret").decode()


def _auth(routes: dict[str, FakeResponse]) -> GigyaAuth:
    return GigyaAuth(make_session(routes))


def test_sign_is_deterministic_and_base64() -> None:
    """The OAuth1 signature is stable for the same inputs and a valid HMAC-SHA1."""
    url = "https://accounts.eu1.gigya.com/accounts.getJWT"
    params = {"apiKey": "4_x", "oauth_token": "st", "timestamp": "1", "nonce": "abc"}
    assert _sign("POST", url, params, _SECRET) == _sign("POST", url, params, _SECRET)
    assert len(base64.b64decode(_sign("POST", url, params, _SECRET))) == 20


def test_sign_changes_with_params() -> None:
    """Different parameters produce a different signature."""
    url = "https://accounts.eu1.gigya.com/accounts.getJWT"
    base = {"apiKey": "4_x", "nonce": "abc"}
    assert _sign("POST", url, base, _SECRET) != _sign(
        "POST", url, {**base, "nonce": "xyz"}, _SECRET
    )


async def test_login_success() -> None:
    """A successful login returns the pool's credentials."""
    auth = _auth(
        {
            "accounts.login": FakeResponse(
                json_data={
                    "errorCode": 0,
                    "sessionInfo": {"sessionToken": "st", "sessionSecret": _SECRET},
                }
            )
        }
    )
    creds = await auth.login("me@example.com", "pw")
    assert creds.session_token == "st"
    assert creds.api_key == "4_VTLGz33ylwYVesXKstwnXw"  # first (COMFORT_EU) pool


async def test_login_all_pools_wrong() -> None:
    """ErrorCode 400093 on every pool raises AuthenticationError."""
    auth = _auth({"accounts.login": FakeResponse(json_data={"errorCode": 400093})})
    with pytest.raises(AuthenticationError):
        await auth.login("me@example.com", "pw")


async def test_login_bad_password_short_circuits() -> None:
    """A non-pool error (bad password) stops probing immediately."""
    auth = _auth(
        {
            "accounts.login": FakeResponse(
                json_data={"errorCode": 403042, "errorMessage": "bad"}
            )
        }
    )
    with pytest.raises(AuthenticationError, match="403042"):
        await auth.login("me@example.com", "pw")


async def test_get_jwt() -> None:
    """GetJWT returns the id_token from a signed request."""
    auth = _auth({"accounts.getJWT": FakeResponse(json_data={"id_token": "a.b.c"})})
    creds = GigyaCredentials(api_key="4_x", session_token="st", session_secret=_SECRET)
    assert await auth.get_jwt(creds) == "a.b.c"
