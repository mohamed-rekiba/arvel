"""PasswordService unit tests.

The service uses the real ``User``, ``PasswordReset``, and ``RefreshToken``
models on in-memory async SQLite.  The plaintext reset token is obtained
from the ``PasswordResetRequested`` event dispatched by ``forgot()``
mirroring how the mail listener gets it in production.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

import pytest
from arvel.auth import (
    PasswordReset,
    PasswordResetCompleted,
    PasswordResetRequested,
    PasswordResetTokenInvalidError,
    PasswordService,
    RefreshToken,
    User,
    hash_refresh_token,
)
from arvel.database.model import Model
from arvel.facades.event import Event as EventFacade
from arvel.facades.hash import Hash
from arvel.testing.fakes.event import EventFake

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession


@pytest.fixture
async def setup_db(engine: AsyncEngine, session: AsyncSession) -> AsyncSession:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    return session


@pytest.fixture
def event_fake() -> EventFake:
    fake = EventFake()
    EventFacade.bind(fake)
    return fake


@pytest.fixture
def password_service() -> PasswordService:
    return PasswordService()


@pytest.fixture
async def alice(setup_db: AsyncSession) -> User:
    """Seed a verified user for password-flow tests."""
    return cast(
        "User",
        await User.create(
            name="Alice",
            email="alice@example.com",
            password=Hash.make("old-password!"),
            email_verified_at=datetime.now(tz=UTC),
        ),
    )


# forgot


@pytest.mark.asyncio
async def test_forgot_known_email_creates_row_and_dispatches_event(
    password_service: PasswordService,
    alice: User,
    event_fake: EventFake,
) -> None:
    """known email → PasswordReset row + PasswordResetRequested event."""
    await password_service.forgot("alice@example.com")

    row = await PasswordReset.where(email="alice@example.com").first()
    assert row is not None
    EventFacade.assert_dispatched(PasswordResetRequested, times=1)
    reset_events = event_fake.dispatched_of(PasswordResetRequested)
    assert reset_events[0].reset_token is not None
    assert len(reset_events[0].reset_token) >= 32
    assert row.token_hash != reset_events[0].reset_token


@pytest.mark.asyncio
async def test_forgot_unknown_email_silent(
    password_service: PasswordService,
    alice: User,
    event_fake: EventFake,
) -> None:
    """unknown email → no row, no event, returns silently."""
    await password_service.forgot("nobody@example.com")

    assert await PasswordReset.where(email="nobody@example.com").first() is None
    EventFacade.assert_not_dispatched(PasswordResetRequested)


@pytest.mark.asyncio
async def test_forgot_throttled_skips_second_token(
    password_service: PasswordService,
    alice: User,
    event_fake: EventFake,
) -> None:
    """second forgot within throttle window → no new row, no new event."""
    await password_service.forgot("alice@example.com")
    EventFacade.assert_dispatched(PasswordResetRequested, times=1)

    await password_service.forgot("alice@example.com")
    # Still only one event fired.
    EventFacade.assert_dispatched(PasswordResetRequested, times=1)


# reset


async def _get_plain_token(
    password_service: PasswordService,
    email: str,
    event_fake: EventFake,
) -> str:
    """Run forgot() and extract the plaintext token from the dispatched event."""
    await password_service.forgot(email)
    events = event_fake.dispatched_of(PasswordResetRequested)
    token = events[-1].reset_token
    assert token is not None
    return token


@pytest.mark.asyncio
async def test_reset_with_valid_token_updates_password_and_burns_row(
    password_service: PasswordService,
    alice: User,
    event_fake: EventFake,
) -> None:
    """successful reset updates user, deletes row."""
    plain = await _get_plain_token(password_service, "alice@example.com", event_fake)

    await password_service.reset(token=plain, password="Brand-New-pw99!")

    assert await PasswordReset.where(email="alice@example.com").first() is None
    updated = await User.where(email="alice@example.com").first()
    assert updated is not None
    assert Hash.check("Brand-New-pw99!", updated.password)
    assert not Hash.check("old-password!", updated.password)
    EventFacade.assert_dispatched(PasswordResetCompleted, times=1)


@pytest.mark.asyncio
async def test_reset_invalid_token_raises(
    password_service: PasswordService,
    alice: User,
    setup_db: AsyncSession,
) -> None:
    """bad token → PasswordResetTokenInvalidError."""
    with pytest.raises(PasswordResetTokenInvalidError):
        await password_service.reset(token="never-minted", password="x" * 12)


@pytest.mark.asyncio
async def test_reset_revokes_all_refresh_tokens(
    password_service: PasswordService,
    alice: User,
    event_fake: EventFake,
) -> None:
    """successful reset deletes every active refresh row for the user."""
    for token_hash in ("a" * 64, "b" * 64):
        await RefreshToken.create(
            user_id=str(alice.id),
            token_hash=token_hash,
            expires_at=datetime.now(tz=UTC) + timedelta(days=14),
        )
    plain = await _get_plain_token(password_service, "alice@example.com", event_fake)
    await password_service.reset(token=plain, password="Brand-New-pw99!")
    assert await RefreshToken.where(user_id=str(alice.id)).first() is None
    assert await RefreshToken.where(token_hash=hash_refresh_token("ignored")).first() is None


@pytest.mark.asyncio
async def test_reset_token_one_shot(
    password_service: PasswordService,
    alice: User,
    event_fake: EventFake,
) -> None:
    """reusing a successful reset token raises."""
    plain = await _get_plain_token(password_service, "alice@example.com", event_fake)

    await password_service.reset(token=plain, password="First-pw99!")
    with pytest.raises(PasswordResetTokenInvalidError):
        await password_service.reset(token=plain, password="Second-pw99!")


@pytest.mark.asyncio
async def test_reset_expired_token_raises_and_cleans_row(
    alice: User,
    event_fake: EventFake,
    setup_db: AsyncSession,
) -> None:
    """Expired (>TTL) token → raises and DELETEs the stale row."""
    short = PasswordService(ttl=timedelta(seconds=-1))
    await short.forgot("alice@example.com")
    events = event_fake.dispatched_of(PasswordResetRequested)
    plain = events[-1].reset_token
    assert plain is not None

    with pytest.raises(PasswordResetTokenInvalidError):
        await short.reset(token=plain, password="x" * 12)
    assert await PasswordReset.where(email="alice@example.com").first() is None
