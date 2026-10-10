"""Verifies a Google OAuth access token by asking Google who it belongs to.

`chrome.identity.getAuthToken` (the extension-side call, Chrome's built-in
flow for a "Chrome Extension"-type OAuth client) hands back an OAuth access
token, not a signed ID token/JWT — so there's no local signature to verify.
Instead, this calls Google's own userinfo endpoint with that token: if it's
valid, Google returns the account's identity; if it's forged, expired, or
was never issued by Google, the call itself fails. That round-trip *is*
the verification — there is no other way to check an opaque access token's
authenticity.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel

_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
_TIMEOUT_SECONDS = 10


class GoogleUserInfo(BaseModel):
    sub: str
    email: str | None = None


class GoogleTokenVerificationError(Exception):
    """The access token was rejected by Google, or the request to verify
    it failed outright (network error, timeout). Either way, sign-in
    cannot proceed — callers should map this to a 401, not a 500, since
    an invalid/expired token is a client-side condition, not a server bug."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


async def verify_google_access_token(access_token: str) -> GoogleUserInfo:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    except httpx.HTTPError as exc:
        raise GoogleTokenVerificationError(f"could not reach Google's userinfo endpoint: {exc}") from exc

    if response.status_code != 200:
        raise GoogleTokenVerificationError(f"Google rejected the access token (status {response.status_code})")

    payload = response.json()
    sub = payload.get("sub")
    if not sub:
        raise GoogleTokenVerificationError("Google's userinfo response had no 'sub' claim")

    return GoogleUserInfo(sub=sub, email=payload.get("email"))
