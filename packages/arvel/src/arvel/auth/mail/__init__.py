"""Auth mailables — verification and password-reset emails.

Both mailables use Jinja2 template names so apps can override them by
providing templates earlier in the Jinja2 FileSystemLoader path chain.
"""

from __future__ import annotations

from arvel.mail.content import Content
from arvel.mail.envelope import Envelope
from arvel.mail.mailable import Mailable


class VerifyEmailMailable(Mailable):
    """sent after registration to confirm the user's email address."""

    def __init__(self, *, user_email: str, verify_url: str, from_address: str = "") -> None:
        self.user_email = user_email
        self.verify_url = verify_url
        # Empty → inherit the app's global mail.from at render time.
        self.from_address = from_address

    def envelope(self) -> Envelope:
        return Envelope(
            from_address=self.from_address,
            to=[self.user_email],
            subject="Verify your email address",
        )

    def content(self) -> Content:
        return Content(
            html_view="auth/emails/verify_email.html.j2",
            text_view="auth/emails/verify_email.txt.j2",
            data={"verify_url": self.verify_url},
        )


class PasswordResetMailable(Mailable):
    """carries a signed reset URL to the user's inbox."""

    def __init__(
        self,
        *,
        user_email: str,
        reset_url: str,
        ttl_minutes: int = 60,
        from_address: str = "",
    ) -> None:
        self.user_email = user_email
        self.reset_url = reset_url
        self.ttl_minutes = ttl_minutes
        # Empty → inherit the app's global mail.from at render time.
        self.from_address = from_address

    def envelope(self) -> Envelope:
        return Envelope(
            from_address=self.from_address,
            to=[self.user_email],
            subject="Reset your password",
        )

    def content(self) -> Content:
        return Content(
            html_view="auth/emails/password_reset.html.j2",
            text_view="auth/emails/password_reset.txt.j2",
            data={"reset_url": self.reset_url, "ttl_minutes": self.ttl_minutes},
        )


__all__ = ["PasswordResetMailable", "VerifyEmailMailable"]
