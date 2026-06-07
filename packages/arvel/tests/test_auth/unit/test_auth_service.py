"""AuthService unit tests.

The service uses the real ``User`` and ``RefreshToken`` models on an
in-memory async SQLite database.  An ``EventFake`` recorder asserts that
the right events are dispatched.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import pytest
from arvel.auth import (
    AccountSuspendedError,
    AuthService,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    LoggedIn,
    LoggedOut,
    LoginFailed,
    RefreshToken,
    Registered,
    TokenReuseDetected,
    TokenReuseDetectedError,
    User,
    hash_refresh_token,
)
from arvel.auth.config import JwtConfig
from arvel.database.model import Model
from arvel.facades.event import Event as EventFacade
from arvel.testing.fakes.event import EventFake

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

_FIXTURE_EMAIL = "alice@example.com"
_FIXTURE_PASSWORD = "S3cret-pw!"


# Fixtures


@pytest.fixture
async def setup_db(engine: AsyncEngine, session: AsyncSession) -> AsyncSession:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    return session


@pytest.fixture
def jwt_secret() -> str:
    return "k" * 32


@pytest.fixture
def event_fake() -> EventFake:
    fake = EventFake()
    EventFacade.bind(fake)
    return fake


@pytest.fixture
def auth_service(jwt_secret: str) -> AuthService:
    return AuthService(jwt=JwtConfig(secret=jwt_secret))


# Helpers


async def _seed_verified_user(
    auth_service: AuthService,
    *,
    email: str = _FIXTURE_EMAIL,
    password: str = _FIXTURE_PASSWORD,
) -> User:
    """Register and mark email verified so login can succeed."""
    user = cast("User", await auth_service.register(name="Alice", email=email, password=password))
    user.email_verified_at = datetime.now(tz=UTC)
    await user.save()
    return user


# Register


@pytest.mark.asyncio
async def test_register_creates_user_and_dispatches_event(
    auth_service: AuthService,
    event_fake: EventFake,
    setup_db: AsyncSession,
) -> None:
    """register persists + dispatches Registered."""
    user = await auth_service.register(name="Ada", email="ADA@example.com", password="S3cret-pw!")

    assert user.email == "ada@example.com"
    assert user.password.startswith("$argon2")
    EventFacade.assert_dispatched(Registered, times=1)
    reg_events = event_fake.dispatched_of(Registered)
    assert reg_events[0].user_id == str(user.id)
    assert reg_events[0].email == "ada@example.com"


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(
    auth_service: AuthService,
    event_fake: EventFake,
    setup_db: AsyncSession,
) -> None:
    """duplicate email surfaces EmailAlreadyRegisteredError."""
    await auth_service.register(name="Bob", email="bob@example.com", password="S3cret-pw!")
    with pytest.raises(EmailAlreadyRegisteredError):
        await auth_service.register(name="Bob2", email="bob@example.com", password="S3cret-pw!")


# Login


@pytest.mark.asyncio
async def test_login_issues_token_pair_for_verified_user(
    auth_service: AuthService,
    event_fake: EventFake,
    setup_db: AsyncSession,
) -> None:
    """happy path: login returns (user, TokenPair)."""
    seeded = await _seed_verified_user(auth_service)

    user, tokens = await auth_service.login(email="alice@example.com", password="S3cret-pw!")

    assert user.id == seeded.id
    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.token_type == "Bearer"
    EventFacade.assert_dispatched(LoggedIn, times=1)
    digest = hash_refresh_token(tokens.refresh_token)
    row = await RefreshToken.where(token_hash=digest).first()
    assert row is not None
    assert row.user_id == str(user.id)


@pytest.mark.asyncio
async def test_login_rejects_unverified_email(
    auth_service: AuthService,
    event_fake: EventFake,
    setup_db: AsyncSession,
) -> None:
    """unverified user → EmailNotVerifiedError + LoginFailed event."""
    await auth_service.register(name="A", email="a@example.com", password="S3cret-pw!")

    with pytest.raises(EmailNotVerifiedError):
        await auth_service.login(email="a@example.com", password="S3cret-pw!")
    EventFacade.assert_dispatched(LoginFailed, times=1)


@pytest.mark.asyncio
async def test_login_rejects_suspended_account(
    auth_service: AuthService,
    event_fake: EventFake,
    setup_db: AsyncSession,
) -> None:
    """suspended_at set → AccountSuspendedError."""
    user = await _seed_verified_user(auth_service)
    user.suspended_at = datetime.now(tz=UTC)
    await user.save()

    with pytest.raises(AccountSuspendedError):
        await auth_service.login(email="alice@example.com", password="S3cret-pw!")


@pytest.mark.asyncio
async def test_login_uniform_401_for_unknown_email_or_bad_password(
    auth_service: AuthService,
    event_fake: EventFake,
    setup_db: AsyncSession,
) -> None:
    """unknown email and wrong password share InvalidCredentialsError."""
    await _seed_verified_user(auth_service)

    with pytest.raises(InvalidCredentialsError):
        await auth_service.login(email="nobody@example.com", password="x" * 12)
    with pytest.raises(InvalidCredentialsError):
        await auth_service.login(email="alice@example.com", password="wrong-password!")


# Refresh


@pytest.mark.asyncio
async def test_refresh_rotates_token(
    auth_service: AuthService,
    event_fake: EventFake,
    setup_db: AsyncSession,
) -> None:
    """refresh revokes the old row (keeps it for reuse detection), stores a new hash."""
    await _seed_verified_user(auth_service)
    _u, first = await auth_service.login(email="alice@example.com", password="S3cret-pw!")

    _u2, second = await auth_service.refresh(refresh_token=first.refresh_token)

    assert second.access_token != first.access_token
    assert second.refresh_token != first.refresh_token
    old_digest = hash_refresh_token(first.refresh_token)
    old_row = await RefreshToken.where(token_hash=old_digest).first()
    assert old_row is not None  # kept, not deleted
    assert old_row.revoked_at is not None
    assert not old_row.is_active
    new_digest = hash_refresh_token(second.refresh_token)
    new_row = await RefreshToken.where(token_hash=new_digest).first()
    assert new_row is not None
    assert new_row.is_active


@pytest.mark.asyncio
async def test_refresh_replay_revokes_token_family(
    auth_service: AuthService,
    event_fake: EventFake,
    setup_db: AsyncSession,
) -> None:
    """Replaying an already-rotated token is treated as theft: kill the family."""
    user = await _seed_verified_user(auth_service)
    _u, first = await auth_service.login(email=user.email, password="S3cret-pw!")
    await auth_service.refresh(refresh_token=first.refresh_token)  # first is now revoked

    with pytest.raises(TokenReuseDetectedError):
        await auth_service.refresh(refresh_token=first.refresh_token)

    assert await RefreshToken.where(user_id=str(user.id)).first() is None
    EventFacade.assert_dispatched(TokenReuseDetected, times=1)


@pytest.mark.asyncio
async def test_refresh_rejects_unknown_token(
    auth_service: AuthService, setup_db: AsyncSession
) -> None:
    with pytest.raises(InvalidCredentialsError):
        await auth_service.refresh(refresh_token="not-a-real-token")


@pytest.mark.asyncio
async def test_revoke_family_raises_and_dispatches_when_rows_present(
    auth_service: AuthService,
    event_fake: EventFake,
    setup_db: AsyncSession,
) -> None:
    """reuse detection helper revokes family + dispatches event."""
    user = await _seed_verified_user(auth_service)
    await auth_service.login(email=user.email, password="S3cret-pw!")
    await auth_service.login(email=user.email, password="S3cret-pw!")

    with pytest.raises(TokenReuseDetectedError):
        await auth_service.revoke_family(user_id=str(user.id))

    assert await RefreshToken.where(user_id=str(user.id)).first() is None
    EventFacade.assert_dispatched(TokenReuseDetected, times=1)


# Logout


@pytest.mark.asyncio
async def test_logout_idempotent_for_missing_or_unknown_token(
    auth_service: AuthService,
    event_fake: EventFake,
    setup_db: AsyncSession,
) -> None:
    """logout swallows missing / unknown tokens silently."""
    await auth_service.logout(refresh_token=None)
    await auth_service.logout(refresh_token="never-issued")
    EventFacade.assert_not_dispatched(LoggedOut)


@pytest.mark.asyncio
async def test_logout_deletes_row_and_dispatches_event(
    auth_service: AuthService,
    event_fake: EventFake,
    setup_db: AsyncSession,
) -> None:
    """Successful logout removes the row + emits LoggedOut."""
    await _seed_verified_user(auth_service)
    _u, tokens = await auth_service.login(email="alice@example.com", password="S3cret-pw!")

    await auth_service.logout(refresh_token=tokens.refresh_token)

    digest = hash_refresh_token(tokens.refresh_token)
    assert await RefreshToken.where(token_hash=digest).first() is None
    EventFacade.assert_dispatched(LoggedOut, times=1)


# Me


@pytest.mark.asyncio
async def test_me_returns_user_for_valid_jwt(
    auth_service: AuthService,
    event_fake: EventFake,
    setup_db: AsyncSession,
) -> None:
    """me() decodes the access JWT and returns the owning user."""
    await _seed_verified_user(auth_service)
    _u, tokens = await auth_service.login(email="alice@example.com", password="S3cret-pw!")

    user = await auth_service.me(access_token=tokens.access_token)
    assert user.email == "alice@example.com"


@pytest.mark.asyncio
async def test_me_rejects_invalid_jwt(auth_service: AuthService, setup_db: AsyncSession) -> None:
    """malformed token → InvalidCredentialsError."""
    with pytest.raises(InvalidCredentialsError):
        await auth_service.me(access_token="not.a.jwt")
