"""Sign in with Apple provider.

Apple is unusual: the ``client_secret`` is a short-lived ES256 JWT signed with
your private key, and identity lives in the ``id_token`` (there's no userinfo
endpoint). We verify the ``id_token`` signature against Apple's published JWKS
rather than trusting it blindly — TLS protects transport, but the JWKS check is
what proves Apple actually minted the token.
"""

from __future__ import annotations

import time
from typing import cast

import httpx
import jwt
from jwt import PyJWK, PyJWKSet

from arvel_oauth.dtos import OAuthToken, OAuthUser
from arvel_oauth.exceptions import OAuthExchangeError
from arvel_oauth.providers.base import OAuthProvider

_AUTHORIZE = "https://appleid.apple.com/auth/authorize"
# OAuth token endpoint URL, not a credential.
_TOKEN = "https://appleid.apple.com/auth/token"  # noqa: S105 # nosec B105
_JWKS = "https://appleid.apple.com/auth/keys"
_ISSUER = "https://appleid.apple.com"
# Audience of the client_secret JWT we sign — same host as the issuer, different claim.
_AUDIENCE = "https://appleid.apple.com"
_SECRET_TTL = 15777000  # ~6 months, Apple's documented maximum.


class AppleProvider(OAuthProvider):
    name = "apple"

    def __init__(
        self,
        *,
        client_id: str,
        team_id: str,
        key_id: str,
        private_key: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
        use_pkce: bool = True,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            client_id=client_id,
            # Apple has no static secret; client_secret_value() signs a JWT per request.
            client_secret="",  # nosec B106
            redirect_uri=redirect_uri,
            authorize_url=_AUTHORIZE,
            token_url=_TOKEN,
            userinfo_url=None,
            scopes=scopes,
            use_pkce=use_pkce,
            http_client=http_client,
        )
        self.team_id = team_id
        self.key_id = key_id
        self.private_key = private_key

    def default_scopes(self) -> list[str]:
        return ["name", "email"]

    def extra_authorize_params(self) -> dict[str, str]:
        # Required when requesting name/email scopes.
        return {"response_mode": "form_post"}

    def client_secret_value(self) -> str:
        now = int(time.time())
        claims: dict[str, object] = {
            "iss": self.team_id,
            "iat": now,
            "exp": now + _SECRET_TTL,
            "aud": _AUDIENCE,
            "sub": self.client_id,
        }
        return jwt.encode(
            claims,
            self.private_key,
            algorithm="ES256",
            headers={"kid": self.key_id},
        )

    async def get_user(self, token: OAuthToken) -> OAuthUser:
        if token.id_token is None:
            raise OAuthExchangeError("Apple token response had no id_token.")
        claims = await self._verify_id_token(token.id_token)
        email = _str_or_none(claims.get("email"))
        return OAuthUser(
            provider=self.name,
            provider_id=str(claims.get("sub", "")),
            email=email,
            email_verified=_apple_bool(claims.get("email_verified")),
            name=None,
            avatar=None,
            raw=dict(claims),
        )

    async def _verify_id_token(self, id_token: str) -> dict[str, object]:
        try:
            kid = jwt.get_unverified_header(id_token).get("kid")
        except jwt.InvalidTokenError as exc:
            raise OAuthExchangeError(f"Apple id_token header is malformed: {exc}") from exc
        if not isinstance(kid, str):
            raise OAuthExchangeError("Apple id_token is missing a 'kid' header.")
        signing_key = await self._signing_key(kid)
        try:
            decoded = jwt.decode(
                id_token,
                signing_key,
                algorithms=["ES256"],
                audience=self.client_id,
                issuer=_ISSUER,
            )
        except jwt.InvalidTokenError as exc:
            raise OAuthExchangeError(f"Apple id_token failed verification: {exc}") from exc
        return cast("dict[str, object]", decoded)

    async def _signing_key(self, kid: str) -> PyJWK:
        async with self._client() as client:
            response = await client.get(_JWKS)
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise OAuthExchangeError(f"Apple JWKS fetch failed (HTTP {response.status_code}).")
        jwks = PyJWKSet.from_dict(self._json(response))
        for key in jwks.keys:
            if key.key_id == kid:
                return key
        raise OAuthExchangeError(f"Apple JWKS has no key for kid {kid!r}.")


def _apple_bool(value: object) -> bool:
    # Apple sends "true"/"false" strings as well as bools.
    if isinstance(value, bool):
        return value
    return value == "true"


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


__all__ = ["AppleProvider"]
