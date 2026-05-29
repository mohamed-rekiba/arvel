"""FR-028-18..22 — EmailVerificationService unit tests.

The service uses the real ``User`` model on in-memory async SQLite.
``consume()`` no longer takes ``ip`` or ``user_agent``.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest
from arvel.auth import (
    EmailVerificationInvalidError,
    EmailVerificationService,
    EmailVerified,
    User,
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
def ev_service() -> EmailVerificationService:
    return EmailVerificationService(secret="secret-key")


@pytest.fixture
async def alice(setup_db: AsyncSession) -> User:
    return cast(
        "User",
        await User.create(
            name="Alice",
            email="alice@example.com",
            password=Hash.make("password"),
        ),
    )


# ─── issue ─────────────────────────────────────────────────────────────────


def test_issue_generates_signed_payload(
    ev_service: EmailVerificationService,
) -> None:
    """FR-028-18 — payload encodes {id, h=sha256(email)[:16]} with HMAC."""
    signed = ev_service.issue(user_id="1", email="alice@example.com")
    assert "." in signed
    user_id, email_hash = ev_service.peek(signed)
    assert user_id == "1"
    assert len(email_hash) == 16


# ─── consume — happy path ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_consume_valid_url_marks_user_verified(
    ev_service: EmailVerificationService,
    alice: User,
    event_fake: EventFake,
) -> None:
    """FR-028-19 — successful consume marks email_verified_at + dispatches event."""
    signed = ev_service.issue(user_id=str(alice.id), email="alice@example.com")
    user = await ev_service.consume(signed)

    assert user.email_verified_at is not None
    EventFacade.assert_dispatched(EmailVerified, times=1)
    ev_events = event_fake.dispatched_of(EmailVerified)
    assert ev_events[0].user_id == str(alice.id)
    assert ev_events[0].email == "alice@example.com"


# ─── consume — failure paths ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_consume_tampered_payload_raises(
    ev_service: EmailVerificationService,
    alice: User,
    event_fake: EventFake,
) -> None:
    """FR-028-22 — tampered signature → EmailVerificationInvalidError."""
    signed = ev_service.issue(user_id=str(alice.id), email="alice@example.com")
    tampered = signed[:-3] + "AAA"
    with pytest.raises(EmailVerificationInvalidError):
        await ev_service.consume(tampered)
    EventFacade.assert_not_dispatched(EmailVerified)


@pytest.mark.asyncio
async def test_consume_expired_payload_raises(alice: User, event_fake: EventFake) -> None:
    """FR-028-22 — expired signature (TTL elapsed) → EmailVerificationInvalidError."""
    short = EmailVerificationService(secret="secret-key", ttl_seconds=1)
    signed = short.issue(user_id=str(alice.id), email="alice@example.com")
    future = time.time() + 60
    with (
        patch("itsdangerous.timed.time.time", return_value=future),
        pytest.raises(EmailVerificationInvalidError),
    ):
        await short.consume(signed)


@pytest.mark.asyncio
async def test_consume_email_changed_after_issue_raises(
    ev_service: EmailVerificationService,
    alice: User,
    event_fake: EventFake,
) -> None:
    """The hash invariant defends against a stale link verifying a new address."""
    signed = ev_service.issue(user_id=str(alice.id), email="alice@example.com")
    alice.email = "alice-new@example.com"
    await alice.save()
    with pytest.raises(EmailVerificationInvalidError):
        await ev_service.consume(signed)


@pytest.mark.asyncio
async def test_consume_unknown_user_raises(
    ev_service: EmailVerificationService,
    setup_db: AsyncSession,
) -> None:
    """Token for a user ID that doesn't exist → EmailVerificationInvalidError."""
    ghost_id = "00000000-0000-0000-0000-000000000001"
    signed = ev_service.issue(user_id=ghost_id, email="ghost@example.com")
    with pytest.raises(EmailVerificationInvalidError):
        await ev_service.consume(signed)
