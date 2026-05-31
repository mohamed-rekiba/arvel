"""GitHub OAuth2 provider.

GitHub isn't OIDC: identity comes from the REST API, and the primary verified
email needs a second call to ``/user/emails`` when the profile email is private.
"""

from __future__ import annotations

from typing import cast

import httpx

from arvel_oauth.dtos import OAuthToken, OAuthUser
from arvel_oauth.exceptions import OAuthExchangeError
from arvel_oauth.providers.base import OAuthProvider

_AUTHORIZE = "https://github.com/login/oauth/authorize"
# OAuth token endpoint URL, not a credential.
_TOKEN = "https://github.com/login/oauth/access_token"  # noqa: S105 # nosec B105
_USER = "https://api.github.com/user"
_EMAILS = "https://api.github.com/user/emails"


class GitHubProvider(OAuthProvider):
    name = "github"

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str] | None = None,
        use_pkce: bool = False,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            authorize_url=_AUTHORIZE,
            token_url=_TOKEN,
            userinfo_url=_USER,
            scopes=scopes,
            use_pkce=use_pkce,
            http_client=http_client,
        )

    def default_scopes(self) -> list[str]:
        return ["read:user", "user:email"]

    async def get_user(self, token: OAuthToken) -> OAuthUser:
        profile = await self._fetch_userinfo(token)
        email, verified = await self._resolve_email(token, profile)
        return OAuthUser(
            provider=self.name,
            provider_id=str(profile.get("id", "")),
            email=email,
            email_verified=verified,
            name=_str_or_none(profile.get("name")) or _str_or_none(profile.get("login")),
            avatar=_str_or_none(profile.get("avatar_url")),
            raw=profile,
        )

    async def _resolve_email(
        self, token: OAuthToken, profile: dict[str, object]
    ) -> tuple[str | None, bool]:
        profile_email = _str_or_none(profile.get("email"))
        if profile_email is not None:
            return profile_email, True
        async with self._client() as client:
            response = await client.get(
                _EMAILS,
                headers={
                    "Authorization": f"Bearer {token.access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise OAuthExchangeError("GitHub email lookup failed.")
        return _pick_primary_email(response.json())


def _pick_primary_email(payload: object) -> tuple[str | None, bool]:
    if not isinstance(payload, list):
        return None, False
    entries = cast("list[object]", payload)
    for entry in entries:
        if isinstance(entry, dict):
            row = cast("dict[object, object]", entry)
            if row.get("primary"):
                return _str_or_none(row.get("email")), bool(row.get("verified", False))
    return None, False


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


__all__ = ["GitHubProvider"]
