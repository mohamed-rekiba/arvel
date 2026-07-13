"""arvel.auth.oauth — OAuth2 / OIDC sign-in on **httpx-oauth** (mandated engine).

Parity glue only: httpx-oauth owns the OAuth2 protocol. ``OAuthProvider`` wraps a generic
OAuth2 client so a controller can build the provider redirect (``authorization_url`` /
``authorize_pkce``) and exchange the callback ``code`` for a token (``access_token``).
Provider-specific clients (Google/GitHub/…) can be passed straight in. httpx-oauth is imported
lazily (the ``[oauth]`` extra), so ``import arvel`` stays light.

**PKCE (RFC 7636)** is supported and recommended: ``authorize_pkce`` mints a ``code_verifier`` +
S256 ``code_challenge``, returns ``(url, verifier)`` for you to stash in the session, and
``access_token(code, redirect_uri, code_verifier=...)`` completes the proof. PKCE binds the callback
``code`` to the client that started the flow, defeating authorization-code interception even for
confidential clients. Grounded in knowledge/port/15-auth-authorization.md.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any


def _b64url(data: bytes) -> str:
    """Base64url without padding (RFC 7636 §A)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_pkce_pair() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` for PKCE S256.

    The verifier is 43 chars of base64url(32 random bytes) — high-entropy and within RFC 7636's
    43-128 range; the challenge is ``base64url(sha256(verifier))``.
    """
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


class OAuthProvider:
    """A thin wrapper over an httpx-oauth OAuth2 client (or any client passed via ``client``)."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        authorize_endpoint: str | None = None,
        access_token_endpoint: str | None = None,
        *,
        scopes: list[str] | None = None,
        client: Any = None,
    ) -> None:
        if client is None:
            from httpx_oauth.oauth2 import OAuth2

            client = OAuth2(
                client_id or "",
                client_secret or "",
                authorize_endpoint or "",
                access_token_endpoint or "",
                base_scopes=scopes,
            )
        self._client = client

    async def authorization_url(
        self,
        redirect_uri: str,
        *,
        state: str | None = None,
        scope: list[str] | None = None,
        code_challenge: str | None = None,
        code_challenge_method: str = "S256",
    ) -> str:
        """Build the provider authorize URL. Pass ``code_challenge`` for PKCE (the method is only
        sent when a challenge is given, so non-PKCE callers are unaffected)."""
        return str(
            await self._client.get_authorization_url(
                redirect_uri,
                state=state,
                scope=scope,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method if code_challenge else None,
            )
        )

    async def authorize_pkce(
        self, redirect_uri: str, *, state: str | None = None, scope: list[str] | None = None
    ) -> tuple[str, str]:
        """Build a PKCE (S256) authorize URL. Returns ``(url, code_verifier)`` — **stash the verifier
        in the session** and hand it to ``access_token`` on the callback."""
        verifier, challenge = generate_pkce_pair()
        url = await self.authorization_url(
            redirect_uri, state=state, scope=scope, code_challenge=challenge
        )
        return url, verifier

    async def access_token(
        self, code: str, redirect_uri: str, *, code_verifier: str | None = None
    ) -> dict[str, Any]:
        """Exchange the callback ``code`` for a token. Pass the ``code_verifier`` from
        ``authorize_pkce`` to complete the PKCE proof."""
        token = await self._client.get_access_token(code, redirect_uri, code_verifier=code_verifier)
        return dict(token)


async def fetch_userinfo(
    access_token: str, userinfo_endpoint: str, *, client: Any = None
) -> dict[str, Any]:
    """Fetch the OIDC/OAuth **userinfo** endpoint with a bearer ``access_token``.

    For plain-OAuth providers (no ``id_token``) this is how you read the profile after the exchange.
    Uses the framework ``http`` client (``arvel.client.Client``) when an app is running, so it shares
    the app's timeouts/instrumentation (and returns a ``ClientResponse``); falls back to a lazy
    ``httpx`` client otherwise (wrapped in the same ``ClientResponse`` for a uniform ``.throw()``/
    ``.json()`` call site). Pass ``client`` to inject one in tests — its ``get()`` must return (or
    await to) a ``ClientResponse``-shaped object. The ``userinfo_endpoint`` **must be https** in
    production — the access token is sent as a bearer header, so a cleartext endpoint would leak it.
    A non-2xx response raises (no partial profile).
    """
    owns = False
    http: Any = client
    if http is None:
        from arvel.kernel import app, has_application

        if has_application():
            try:
                http = app("http")  # framework Client — container-owned, opens/closes per call
            except Exception:
                http = None
        if http is None:
            import httpx

            http = httpx.AsyncClient()  # self-created → we must close it
            owns = True
    try:
        raw: Any = await http.get(
            userinfo_endpoint, headers={"Authorization": f"Bearer {access_token}"}
        )
        response: Any = raw
        if owns:
            from arvel.client import ClientResponse

            response = ClientResponse(raw)
        response.throw()
        return dict(response.json())
    finally:
        if owns:
            await http.aclose()


__all__ = ["OAuthProvider", "fetch_userinfo", "generate_pkce_pair"]
