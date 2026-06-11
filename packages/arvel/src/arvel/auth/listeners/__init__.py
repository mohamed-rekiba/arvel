"""Default auth event listeners — wired by ``AuthServiceProvider.boot()``."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from arvel.auth.events import PasswordResetRequested, Registered
from arvel.events.listener import Listener

if TYPE_CHECKING:
    from arvel.auth.email_verification_service import EmailVerificationService

_log = logging.getLogger("arvel.auth")

# Set by AuthServiceProvider._wire_ev_service() so the default listener can
# compose signed verification URLs without constructor injection.
_ev_service: EmailVerificationService | None = None


def _set_ev_service(svc: EmailVerificationService) -> None:
    global _ev_service  # noqa: PLW0603
    _ev_service = svc


class SendVerificationEmail(Listener[Registered]):
    """Send a verification email when a new user registers."""

    async def handle(self, event: Registered) -> None:
        from arvel.auth.mail import VerifyEmailMailable  # noqa: PLC0415
        from arvel.facades.mail import Mail  # noqa: PLC0415

        if _ev_service is None or event.user_id is None:
            return
        try:
            from arvel.config import config  # noqa: PLC0415

            app_url = config("app.url", "http://localhost:8000")
            signed = _ev_service.issue(user_id=event.user_id, email=event.email)
            verify_url = _ev_service.build_url(
                base_url=f"{app_url}/api/auth/verify",
                signed=signed,
            )
            mailable = VerifyEmailMailable(user_email=event.email, verify_url=verify_url)
            await Mail.to(event.email).send(mailable)
        except Exception:  # noqa: BLE001
            _log.exception("SendVerificationEmail: failed to send for %s", event.email)


class SendPasswordResetEmail(Listener[PasswordResetRequested]):
    """Send a password reset email when a reset is requested."""

    async def handle(self, event: PasswordResetRequested) -> None:
        from arvel.auth.mail import PasswordResetMailable  # noqa: PLC0415
        from arvel.facades.mail import Mail  # noqa: PLC0415

        if event.reset_token is None:
            return
        try:
            reset_url = _build_reset_url(token=event.reset_token, email=event.email)
            mailable = PasswordResetMailable(user_email=event.email, reset_url=reset_url)
            await Mail.to(event.email).send(mailable)
        except Exception:  # noqa: BLE001
            _log.exception("SendPasswordResetEmail: failed to send for %s", event.email)


def _build_reset_url(*, token: str, email: str) -> str:
    """Compose the front-end reset link, appending token + email query params.

    Base comes from ``auth.reset_page_url``; empty falls back to ``{app.url}/reset-password``.
    """
    from arvel.config import config  # noqa: PLC0415

    base = config("auth.reset_page_url", "")
    if not base:
        base = f"{config('app.url', 'http://localhost:8000')}/reset-password"

    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["token"] = token
    query["email"] = email
    return urlunsplit(parts._replace(query=urlencode(query)))


__all__ = [
    "SendPasswordResetEmail",
    "SendVerificationEmail",
    "_build_reset_url",
    "_set_ev_service",
]
