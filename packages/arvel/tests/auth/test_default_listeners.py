"""Default auth listener behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from arvel.auth.email_verification_service import EmailVerificationService
from arvel.auth.events import PasswordResetRequested, Registered
from arvel.auth.listeners import (
    SendPasswordResetEmail,
    SendVerificationEmail,
    _set_ev_service,
)


class _VerificationService:
    def issue(self, *, user_id: str, email: str) -> str:
        return f"{user_id}:{email}:signed"

    def build_url(self, *, base_url: str, signed: str) -> str:
        return f"{base_url}?signed={signed}"


async def test_verification_listener_returns_without_service_or_user() -> None:
    listener = SendVerificationEmail()
    event = Registered(user_id=None, email="user@example.com", occurred_at=datetime.now(tz=UTC))

    await listener.handle(event)


async def test_verification_listener_swallows_mail_failures() -> None:
    _set_ev_service(cast("EmailVerificationService", _VerificationService()))
    listener = SendVerificationEmail()
    event = Registered(user_id="u1", email="user@example.com", occurred_at=datetime.now(tz=UTC))

    await listener.handle(event)


async def test_password_reset_listener_returns_without_token() -> None:
    listener = SendPasswordResetEmail()
    event = PasswordResetRequested(
        user_id="u1",
        email="user@example.com",
        occurred_at=datetime.now(tz=UTC),
        reset_token=None,
    )

    await listener.handle(event)


async def test_password_reset_listener_swallows_mail_failures() -> None:
    listener = SendPasswordResetEmail()
    event = PasswordResetRequested(
        user_id="u1",
        email="user@example.com",
        occurred_at=datetime.now(tz=UTC),
        reset_token="reset-token",
    )

    await listener.handle(event)
