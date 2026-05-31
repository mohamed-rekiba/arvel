"""Link provider identities to host users."""

from __future__ import annotations

import secrets
from typing import Any

from arvel.auth.models.user import User
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from arvel_oauth.dtos import OAuthToken, OAuthUser
from arvel_oauth.exceptions import DuplicateOAuthAccount
from arvel_oauth.models import OAuthAccount


class OAuthAccountLinker:
    """Resolves a host user for an :class:`OAuthUser`, creating links as needed."""

    def __init__(self, session: AsyncSession, *, user_model: type[User] = User) -> None:
        self._session = session
        self._user_model = user_model

    async def link(self, oauth_user: OAuthUser, token: OAuthToken) -> OAuthAccount:
        """Find-or-create the OAuthAccount + User for this identity.

        Existing links are refreshed (tokens updated). First-time identities
        attach to an existing user with the same *verified* email, or create a
        new user otherwise.
        """
        existing = await self._find_account(oauth_user)
        if existing is not None:
            existing.tokens = _token_dict(token)
            await self._session.flush()
            return existing

        user = await self._resolve_user(oauth_user)
        account = OAuthAccount(
            user_id=user.id,
            provider=oauth_user.provider,
            provider_id=oauth_user.provider_id,
            tokens=_token_dict(token),
        )
        self._session.add(account)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise DuplicateOAuthAccount(oauth_user.provider, oauth_user.provider_id) from exc
        return account

    async def _find_account(self, oauth_user: OAuthUser) -> OAuthAccount | None:
        stmt = select(OAuthAccount).where(
            OAuthAccount.provider == oauth_user.provider,
            OAuthAccount.provider_id == oauth_user.provider_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _resolve_user(self, oauth_user: OAuthUser) -> User:
        if oauth_user.email and oauth_user.email_verified:
            stmt = select(self._user_model).where(self._user_model.email == oauth_user.email)
            result = await self._session.execute(stmt)
            match = result.scalar_one_or_none()
            if match is not None:
                return match
        return await self._create_user(oauth_user)

    async def _create_user(self, oauth_user: OAuthUser) -> User:
        # Only adopt the provider email as the account's unique email when it's
        # verified — otherwise an unverified claim could hijack an existing row.
        if oauth_user.email and oauth_user.email_verified:
            email = oauth_user.email
        else:
            email = f"{oauth_user.provider_id}@{oauth_user.provider}.local"
        # OAuth users have no password; store an unusable random hash placeholder.
        user = self._user_model(
            name=oauth_user.name or (oauth_user.email or oauth_user.provider_id),
            email=email,
            password=secrets.token_urlsafe(32),
        )
        self._session.add(user)
        await self._session.flush()
        return user


def _token_dict(token: OAuthToken) -> dict[str, Any]:
    return token.model_dump(exclude={"raw"})


__all__ = ["OAuthAccountLinker"]
