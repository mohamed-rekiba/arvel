"""OAuthController — redirect + callback for the OAuth2 dance.

The ``state`` and PKCE ``code_verifier`` are kept server-side in ``HttpOnly``,
``SameSite=Lax`` cookies and checked on the callback — never trusted from the
query string alone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.context import Context
from arvel.database.db import DB
from arvel.http.exceptions import ValidationException
from fastapi.responses import RedirectResponse
from starlette.requests import Request
from starlette.responses import Response

from arvel_oauth.linker import OAuthAccountLinker
from arvel_oauth.pkce import code_challenge_s256, generate_code_verifier, generate_state
from arvel_oauth.providers.base import OAuthProvider

if TYPE_CHECKING:
    from arvel.auth.auth_service import AuthService

    from arvel_oauth.config import OAuthConfig
    from arvel_oauth.manager import OAuthManager

_STATE_COOKIE = "oauth_state"
_PKCE_COOKIE = "oauth_pkce"
_COOKIE_MAX_AGE = 600  # OAuth round-trip should finish well within 10 minutes.


class OAuthController:
    def __init__(
        self,
        *,
        manager: OAuthManager,
        config: OAuthConfig,
        auth: AuthService,
        cookie_secure: bool = True,
    ) -> None:
        self._manager = manager
        self._config = config
        self._auth = auth
        self._cookie_secure = cookie_secure

    async def redirect(self, provider_name: str) -> RedirectResponse:
        provider = await self._resolve(provider_name)
        state = generate_state()
        verifier = generate_code_verifier() if provider.use_pkce else ""
        challenge = code_challenge_s256(verifier) if provider.use_pkce else None
        url = provider.get_authorization_url(state, challenge)

        response = RedirectResponse(url, status_code=307)
        self._set_cookie(response, _STATE_COOKIE, state)
        if provider.use_pkce:
            self._set_cookie(response, _PKCE_COOKIE, verifier)
        return response

    async def callback(self, provider_name: str, request: Request) -> Response:
        error = request.query_params.get("error")
        if error is not None:
            return RedirectResponse(self._config.error_redirect_url, status_code=303)

        code = request.query_params.get("code")
        state = request.query_params.get("state")
        cookie_state = request.cookies.get(_STATE_COOKIE)
        if not code or not state or not cookie_state or state != cookie_state:
            raise ValidationException("Invalid or missing OAuth state.")

        provider = await self._resolve(provider_name)
        verifier = request.cookies.get(_PKCE_COOKIE) if provider.use_pkce else None
        token = await provider.exchange_code(code, verifier)
        oauth_user = await provider.get_user(token)

        async with DB.transaction() as session:
            account = await OAuthAccountLinker(session).link(oauth_user, token)
            user_id = account.user_id

        pair = await self._auth.issue_for(user_id=user_id, email=oauth_user.email or "")
        Context.add("user_id", user_id)

        response: Response = RedirectResponse(self._config.success_redirect_url, status_code=303)
        response.set_cookie(
            "access_token",
            pair.access_token,
            httponly=True,
            secure=self._cookie_secure,
            samesite="lax",
        )
        response.delete_cookie(_STATE_COOKIE)
        response.delete_cookie(_PKCE_COOKIE)
        return response

    async def _resolve(self, provider_name: str) -> OAuthProvider:
        if provider_name == "oidc":
            return await self._manager.oidc()
        return self._manager.provider(provider_name)

    def _set_cookie(self, response: Response, name: str, value: str) -> None:
        response.set_cookie(
            name,
            value,
            max_age=_COOKIE_MAX_AGE,
            httponly=True,
            secure=self._cookie_secure,
            samesite="lax",
        )


__all__ = ["OAuthController"]
