"""Google OAuth2/OIDC provider."""

from __future__ import annotations

import httpx

from arvel_auth_social.dtos import OAuthToken, OAuthUser
from arvel_auth_social.providers.base import OAuthProvider

_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
# OAuth token endpoint URL, not a credential.
_TOKEN = "https://oauth2.googleapis.com/token"  # noqa: S105 # nosec B105
_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"


class GoogleProvider(OAuthProvider):
    name = "google"

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
        use_pkce: bool = True,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            authorize_url=_AUTHORIZE,
            token_url=_TOKEN,
            userinfo_url=_USERINFO,
            scopes=scopes,
            use_pkce=use_pkce,
            http_client=http_client,
        )

    def extra_authorize_params(self) -> dict[str, str]:
        # access_type=offline gets a refresh token; prompt forces re-consent.
        return {"access_type": "offline", "prompt": "consent"}

    async def get_user(self, token: OAuthToken) -> OAuthUser:
        data = await self._fetch_userinfo(token)
        return OAuthUser(
            provider=self.name,
            provider_id=str(data.get("sub", "")),
            email=_str_or_none(data.get("email")),
            email_verified=bool(data.get("email_verified", False)),
            name=_str_or_none(data.get("name")),
            avatar=_str_or_none(data.get("picture")),
            raw=data,
        )


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


__all__ = ["GoogleProvider"]
