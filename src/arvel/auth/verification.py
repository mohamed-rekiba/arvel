"""Email verification — MustVerifyEmail protocol and verification service."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from arvel.mail.mailable import Mailable

if TYPE_CHECKING:
    from arvel.http.url import UrlGenerator
    from arvel.mail.contracts import MailContract


@runtime_checkable
class MustVerifyEmail(Protocol):
    """Protocol for models that require email verification.

    User models implement this to opt into the verification flow.
    The framework checks ``is_verified`` and calls ``mark_as_verified()``.
    """

    @property
    def email(self) -> str: ...

    @property
    def is_verified(self) -> bool: ...

    def mark_as_verified(self) -> None: ...


class VerificationEmail(Mailable):
    """Email containing the verification signed URL."""

    subject: str = "Verify your email address"


class EmailVerificationService:
    """Manages email verification flow — send, verify, rate-limit resend."""

    def __init__(
        self,
        *,
        url_generator: UrlGenerator,
        mail: MailContract,
        route_name: str = "verification.verify",
        expiry_minutes: int = 60,
        resend_cooldown_seconds: int = 60,
    ) -> None:
        self._url_generator = url_generator
        self._mail = mail
        self._route_name = route_name
        self._expiry_minutes = expiry_minutes
        self._resend_cooldown = resend_cooldown_seconds
        self._last_sent: dict[str, float] = {}

    def _generate_verification_url(self, user_id: str) -> str:
        return self._url_generator.signed_url(
            self._route_name,
            expires=self._expiry_minutes * 60,
            user_id=user_id,
        )

    async def send_verification(self, user: MustVerifyEmail, *, user_id: str) -> None:
        """Send a verification email with a signed URL."""
        url = self._generate_verification_url(user_id)

        email = VerificationEmail(
            to=[user.email],
            body=f"Verify your email: {url}",
            html_body=f'<a href="{url}">Verify your email</a>',
        )
        await self._mail.send(email)
        self._last_sent[user_id] = time.monotonic()

    def verify_url(self, url: str) -> str:
        """Validate a verification URL and return the user_id.

        Raises InvalidSignatureError on invalid/expired URLs.
        """
        self._url_generator.validate_signature(url)

        from urllib.parse import urlparse

        parsed = urlparse(url)
        path_parts = parsed.path.rstrip("/").split("/")
        return path_parts[-1]

    def can_resend(self, user_id: str) -> bool:
        """Check if a verification email can be resent (rate limiting)."""
        last = self._last_sent.get(user_id)
        if last is None:
            return True
        return (time.monotonic() - last) >= self._resend_cooldown
