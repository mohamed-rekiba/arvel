"""Tests for email verification flow — MustVerifyEmail, EmailVerificationService."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from arvel.auth.verification import EmailVerificationService
from arvel.http.url import UrlGenerator
from arvel.mail.fakes import MailFake


@dataclass
class FakeVerifiableUser:
    """Test model implementing MustVerifyEmail."""

    id: str
    email: str
    email_verified_at: datetime | None = None

    @property
    def is_verified(self) -> bool:
        return self.email_verified_at is not None

    def mark_as_verified(self) -> None:
        self.email_verified_at = datetime.now(UTC)


def _make_router():
    from arvel.http.router import Router

    router = Router()
    router.get("/email/verify/{user_id}", lambda r: None, name="verification.verify")
    return router


def _make_url_generator() -> UrlGenerator:
    router = _make_router()
    return UrlGenerator(router, app_key="test-app-key-for-signing", base_url="https://app.test")


def _make_service(mail: MailFake | None = None) -> tuple[EmailVerificationService, MailFake]:
    mail_fake = mail or MailFake()
    url_gen = _make_url_generator()
    service = EmailVerificationService(
        url_generator=url_gen,
        mail=mail_fake,
        route_name="verification.verify",
        expiry_minutes=60,
    )
    return service, mail_fake


class TestMustVerifyEmailProtocol:
    def test_unverified_user_is_not_verified(self) -> None:
        user = FakeVerifiableUser(id="u1", email="alice@test.com")

        assert user.is_verified is False
        assert user.email_verified_at is None

    def test_mark_as_verified_sets_timestamp(self) -> None:
        user = FakeVerifiableUser(id="u1", email="alice@test.com")

        user.mark_as_verified()

        assert user.is_verified is True
        assert user.email_verified_at is not None

    def test_already_verified_stays_verified(self) -> None:
        user = FakeVerifiableUser(id="u1", email="alice@test.com")
        user.mark_as_verified()

        user.mark_as_verified()

        assert user.is_verified is True


class TestEmailVerificationService:
    async def test_send_verification_dispatches_email(self) -> None:
        """FR-009: Verification email sent via MailContract."""
        service, mail = _make_service()
        user = FakeVerifiableUser(id="u1", email="alice@test.com")

        await service.send_verification(user, user_id="u1")

        assert mail.sent_count == 1
        mail.assert_sent_to("alice@test.com")

    async def test_send_verification_includes_signed_url(self) -> None:
        service, mail = _make_service()
        user = FakeVerifiableUser(id="u1", email="alice@test.com")

        await service.send_verification(user, user_id="u1")

        assert mail.sent_count == 1
        sent = mail._sent[0]
        assert "signature=" in sent.body or "signature=" in sent.html_body

    async def test_verify_url_returns_user_id(self) -> None:
        """FR-010a: Valid signed URL verifies successfully."""
        service, _mail = _make_service()
        url = service._generate_verification_url("u1")

        user_id = service.verify_url(url)

        assert user_id == "u1"

    async def test_verify_expired_url_raises(self) -> None:
        """FR-010b: Expired URL returns error."""
        service, _mail = _make_service()
        url_gen = _make_url_generator()
        expired_url = url_gen.signed_url("verification.verify", expires=-1, user_id="u1")

        with pytest.raises(Exception, match=r"expired|invalid"):
            service.verify_url(expired_url)

    async def test_verify_tampered_url_raises(self) -> None:
        service, _mail = _make_service()
        url = service._generate_verification_url("u1")
        tampered = url.replace("u1", "u2")

        with pytest.raises(Exception, match=r"invalid|signature"):
            service.verify_url(tampered)

    async def test_resend_rate_limit_blocks_fast_resend(self) -> None:
        """FR-012a: Resend within 60 seconds is blocked."""
        service, _mail = _make_service()
        user = FakeVerifiableUser(id="u1", email="alice@test.com")

        await service.send_verification(user, user_id="u1")
        can_resend = service.can_resend("u1")

        assert can_resend is False

    async def test_resend_allowed_after_cooldown(self) -> None:
        """FR-012b: Resend after 60 seconds is allowed."""
        service, _mail = _make_service()

        assert service.can_resend("u1") is True
