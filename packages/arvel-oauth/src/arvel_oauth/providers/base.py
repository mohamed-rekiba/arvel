"""OAuthProvider — base class for all OAuth providers.

Subclasses declare endpoints and scopes and implement ``get_user``. The base
builds the authorization URL (with PKCE by default) and performs the
authorization-code exchange over httpx. Inject an ``httpx.AsyncClient`` to test
without network access.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from typing import cast
from urllib.parse import urlencode

import httpx

from arvel_oauth.dtos import OAuthToken, OAuthUser
from arvel_oauth.exceptions import OAuthExchangeError


class OAuthProvider(ABC):
    name: str = "oauth"

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        authorize_url: str,
        token_url: str,
        userinfo_url: str | None = None,
        scopes: list[str] | None = None,
        use_pkce: bool = True,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.authorize_url = authorize_url
        self.token_url = token_url
        self.userinfo_url = userinfo_url
        self.scopes = scopes or self.default_scopes()
        self.use_pkce = use_pkce
        self._http_client = http_client

    def default_scopes(self) -> list[str]:
        return ["openid", "email", "profile"]

    def get_authorization_url(self, state: str, code_challenge: str | None = None) -> str:
        params: dict[str, str] = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
        }
        if self.use_pkce and code_challenge is not None:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        params.update(self.extra_authorize_params())
        return f"{self.authorize_url}?{urlencode(params)}"

    def extra_authorize_params(self) -> dict[str, str]:
        """Provider-specific authorize params (e.g. ``access_type=offline``)."""
        return {}

    async def exchange_code(self, code: str, code_verifier: str | None = None) -> OAuthToken:
        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret_value(),
        }
        if self.use_pkce and code_verifier is not None:
            data["code_verifier"] = code_verifier

        async with self._client() as client:
            response = await client.post(
                self.token_url,
                data=data,
                headers={"Accept": "application/json"},
            )
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise OAuthExchangeError(
                f"{self.name} token exchange failed (HTTP {response.status_code})."
            )
        payload = self._json(response)
        return OAuthToken(
            access_token=str(payload.get("access_token", "")),
            token_type=str(payload.get("token_type", "Bearer")),
            expires_in=_as_int(payload.get("expires_in")),
            refresh_token=_as_opt_str(payload.get("refresh_token")),
            id_token=_as_opt_str(payload.get("id_token")),
            scope=_as_opt_str(payload.get("scope")),
            raw=payload,
        )

    def client_secret_value(self) -> str:
        """The credential sent as ``client_secret``. Apple overrides with a signed JWT."""
        return self.client_secret

    @abstractmethod
    async def get_user(self, token: OAuthToken) -> OAuthUser:
        """Resolve the normalized identity for ``token``."""

    async def _fetch_userinfo(self, token: OAuthToken) -> dict[str, object]:
        if self.userinfo_url is None:
            raise OAuthExchangeError(f"{self.name} has no userinfo endpoint configured.")
        async with self._client() as client:
            response = await client.get(
                self.userinfo_url,
                headers={"Authorization": f"Bearer {token.access_token}"},
            )
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise OAuthExchangeError(
                f"{self.name} userinfo request failed (HTTP {response.status_code})."
            )
        return self._json(response)

    def _client(self) -> AbstractAsyncContextManager[httpx.AsyncClient]:
        if self._http_client is not None:
            return _BorrowedClient(self._http_client)
        return httpx.AsyncClient(timeout=10.0)

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, object]:
        parsed: object = response.json()
        if not isinstance(parsed, dict):
            raise OAuthExchangeError("Provider returned a non-object JSON body.")
        items = cast("dict[object, object]", parsed)
        return {str(k): v for k, v in items.items()}


class _BorrowedClient:
    """Async-context wrapper that yields an injected client without closing it."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self._client

    async def __aexit__(self, *args: object) -> None:
        return None


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _as_opt_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


__all__ = ["OAuthProvider"]
