"""Generic OIDC provider with .well-known auto-discovery."""

from __future__ import annotations

from typing import cast

import httpx2 as httpx

from arvel_oauth.dtos import OAuthToken, OAuthUser
from arvel_oauth.exceptions import OIDCDiscoveryError
from arvel_oauth.providers.base import OAuthProvider

_DISCOVERY_SUFFIX = "/.well-known/openid-configuration"


class OIDCProvider(OAuthProvider):
    """A standards-compliant OIDC client configured from a discovery document."""

    name = "oidc"

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        authorize_url: str,
        token_url: str,
        userinfo_url: str | None = None,
        name: str = "oidc",
        scopes: list[str] | None = None,
        use_pkce: bool = True,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = name
        super().__init__(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            authorize_url=authorize_url,
            token_url=token_url,
            userinfo_url=userinfo_url,
            scopes=scopes,
            use_pkce=use_pkce,
            http_client=http_client,
        )

    @classmethod
    async def discover(
        cls,
        *,
        issuer: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        name: str = "oidc",
        scopes: list[str] | None = None,
        use_pkce: bool = True,
        allow_http: bool = False,
        http_client: httpx.AsyncClient | None = None,
    ) -> OIDCProvider:
        """Build a provider by fetching the issuer's discovery document."""
        _guard_issuer_scheme(issuer, allow_http=allow_http)
        document = await _fetch_discovery(issuer, http_client)
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            authorize_url=_require(document, "authorization_endpoint", issuer),
            token_url=_require(document, "token_endpoint", issuer),
            userinfo_url=_optional(document, "userinfo_endpoint"),
            name=name,
            scopes=scopes,
            use_pkce=use_pkce,
            http_client=http_client,
        )

    async def get_user(self, token: OAuthToken) -> OAuthUser:
        data = await self._fetch_userinfo(token)
        email = _str_or_none(data.get("email"))
        return OAuthUser(
            provider=self.name,
            provider_id=str(data.get("sub", "")),
            email=email,
            email_verified=bool(data.get("email_verified", False)),
            name=_str_or_none(data.get("name")) or _str_or_none(data.get("preferred_username")),
            avatar=_str_or_none(data.get("picture")),
            raw=data,
        )


def _guard_issuer_scheme(issuer: str, *, allow_http: bool) -> None:
    # Discovery and token exchange leak credentials over plaintext — HTTPS only,
    # unless explicitly opted out for local dev.
    if issuer.startswith("https://"):
        return
    if issuer.startswith("http://") and allow_http:
        return
    raise OIDCDiscoveryError(
        issuer, "issuer must use https (set OAUTH_ALLOW_HTTP_ISSUER=true for local dev)"
    )


async def _fetch_discovery(issuer: str, http_client: httpx.AsyncClient | None) -> dict[str, object]:
    url = issuer.rstrip("/") + _DISCOVERY_SUFFIX
    client = http_client or httpx.AsyncClient(timeout=10.0)
    own = http_client is None
    try:
        response = await client.get(url)
    except httpx.HTTPError as exc:
        raise OIDCDiscoveryError(issuer, str(exc)) from exc
    finally:
        if own:
            await client.aclose()
    if response.status_code >= httpx.codes.BAD_REQUEST:
        raise OIDCDiscoveryError(issuer, f"HTTP {response.status_code}")
    parsed: object = response.json()
    if not isinstance(parsed, dict):
        raise OIDCDiscoveryError(issuer, "discovery document is not a JSON object")
    items = cast("dict[object, object]", parsed)
    return {str(k): v for k, v in items.items()}


def _require(document: dict[str, object], key: str, issuer: str) -> str:
    value = document.get(key)
    if not isinstance(value, str):
        raise OIDCDiscoveryError(issuer, f"missing {key!r} in discovery document")
    return value


def _optional(document: dict[str, object], key: str) -> str | None:
    value = document.get(key)
    return value if isinstance(value, str) else None


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


__all__ = ["OIDCProvider"]
