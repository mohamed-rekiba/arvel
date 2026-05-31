"""Sign in with Apple provider.

Apple is unusual: the ``client_secret`` is a short-lived ES256 JWT signed with
your private key, and identity lives in the ``id_token`` (there's no userinfo
endpoint). Per OIDC core, an ``id_token`` received directly from the token
endpoint over TLS may be trusted without re-verifying the signature.
"""

from __future__ import annotations

import time
from typing import cast

import httpx
import jwt

from arvel_oauth.dtos import OAuthToken, OAuthUser
from arvel_oauth.exceptions import OAuthExchangeError
from arvel_oauth.providers.base import OAuthProvider

_AUTHORIZE = "https://appleid.apple.com/auth/authorize"
# OAuth token endpoint URL, not a credential.
_TOKEN = "https://appleid.apple.com/auth/token"  # noqa: S105 # nosec B105
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
        claims = cast(
            "dict[str, object]",
            jwt.decode(
                token.id_token,
                options={"verify_signature": False},
                audience=self.client_id,
            ),
        )
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


def _apple_bool(value: object) -> bool:
    # Apple sends "true"/"false" strings as well as bools.
    if isinstance(value, bool):
        return value
    return value == "true"


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


__all__ = ["AppleProvider"]
