"""Microsoft Entra ID (Azure AD) OAuth2/OIDC provider."""

from __future__ import annotations

import httpx2 as httpx

from arvel_oauth.dtos import OAuthToken, OAuthUser
from arvel_oauth.providers.base import OAuthProvider

_GRAPH_ME = "https://graph.microsoft.com/oidc/userinfo"


class MicrosoftProvider(OAuthProvider):
    name = "microsoft"

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        tenant: str = "common",
        scopes: list[str] | None = None,
        use_pkce: bool = True,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
        super().__init__(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            authorize_url=f"{base}/authorize",
            token_url=f"{base}/token",
            userinfo_url=_GRAPH_ME,
            scopes=scopes,
            use_pkce=use_pkce,
            http_client=http_client,
        )

    async def get_user(self, token: OAuthToken) -> OAuthUser:
        data = await self._fetch_userinfo(token)
        email = _str_or_none(data.get("email")) or _str_or_none(data.get("preferred_username"))
        return OAuthUser(
            provider=self.name,
            provider_id=str(data.get("sub", "")),
            email=email,
            email_verified=bool(data.get("email_verified", email is not None)),
            name=_str_or_none(data.get("name")),
            avatar=_str_or_none(data.get("picture")),
            raw=data,
        )


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


__all__ = ["MicrosoftProvider"]
