"""OAuthAccountLinker — user resolution, link reuse, and duplicate protection."""

from __future__ import annotations

import pytest
from arvel.auth.models.user import User
from arvel_oauth.dtos import OAuthToken, OAuthUser
from arvel_oauth.exceptions import DuplicateOAuthAccount
from arvel_oauth.linker import OAuthAccountLinker
from arvel_oauth.models import OAuthAccount
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_TOKEN = OAuthToken(access_token="at", refresh_token="rt")


def _oauth_user(**overrides: object) -> OAuthUser:
    user = OAuthUser(
        provider="google",
        provider_id="g-1",
        email="new@example.com",
        email_verified=True,
        name="New User",
    )
    if overrides:
        return user.model_copy(update=overrides)
    return user


async def test_first_login_creates_user_and_account(async_session: AsyncSession) -> None:
    account = await OAuthAccountLinker(async_session).link(_oauth_user(), _TOKEN)
    assert account.provider == "google"
    assert account.provider_id == "g-1"
    assert account.tokens is not None
    assert account.tokens["access_token"] == "at"

    user = await async_session.get(User, account.user_id)
    assert user is not None
    assert user.email == "new@example.com"


async def test_links_to_existing_verified_email(async_session: AsyncSession) -> None:
    existing = User(name="Existing", email="known@example.com", password="x")
    async_session.add(existing)
    await async_session.flush()

    account = await OAuthAccountLinker(async_session).link(
        _oauth_user(email="known@example.com"), _TOKEN
    )
    assert account.user_id == existing.id


async def test_unverified_email_does_not_link(async_session: AsyncSession) -> None:
    existing = User(name="Existing", email="known@example.com", password="x")
    async_session.add(existing)
    await async_session.flush()

    account = await OAuthAccountLinker(async_session).link(
        _oauth_user(email="known@example.com", email_verified=False), _TOKEN
    )
    assert account.user_id != existing.id


async def test_repeat_login_updates_existing_account(async_session: AsyncSession) -> None:
    linker = OAuthAccountLinker(async_session)
    first = await linker.link(_oauth_user(), _TOKEN)
    second = await linker.link(_oauth_user(), OAuthToken(access_token="at2"))
    assert first.id == second.id
    assert second.tokens is not None
    assert second.tokens["access_token"] == "at2"

    rows = (await async_session.execute(select(OAuthAccount))).scalars().all()
    assert len(rows) == 1


async def test_unique_constraint_blocks_duplicate_link(async_session: AsyncSession) -> None:
    from sqlalchemy.exc import IntegrityError

    await OAuthAccountLinker(async_session).link(_oauth_user(), _TOKEN)

    # A raw duplicate (provider, provider_id) for another user must be rejected.
    other = User(name="Other", email="other@example.com", password="x")
    async_session.add(other)
    await async_session.flush()
    async_session.add(OAuthAccount(user_id=other.id, provider="google", provider_id="g-1"))
    with pytest.raises(IntegrityError):
        await async_session.flush()


def test_duplicate_exception_message() -> None:
    exc = DuplicateOAuthAccount("google", "g-1")
    assert exc.provider == "google"
    assert exc.provider_id == "g-1"
    assert "google:g-1" in str(exc)
