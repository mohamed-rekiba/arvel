"""``AuthController`` — thin HTTP façade over the auth services.

Responsibilities:

- Parse requests → service call → format response.
- Map service domain errors to :class:`HttpException` subclasses.
- Set / clear the ``__Host-refresh`` (HttpOnly) and ``_csrf`` (readable)
  cookie pair on login, refresh, and logout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from fastapi import Response
from fastapi.responses import JSONResponse, RedirectResponse

from arvel.auth.exceptions import (
    AccountSuspendedError,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    EmailVerificationInvalidError,
    InvalidCredentialsError,
    PasswordResetTokenInvalidError,
    TokenReuseDetectedError,
)
from arvel.auth.http.requests import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
)
from arvel.auth.http.resources import AuthEnvelope, LoginResponse, UserResource
from arvel.http.controller import Controller
from arvel.http.exceptions import (
    AuthorizationException,
    ConflictException,
    UnauthenticatedException,
    ValidationException,
)

if TYPE_CHECKING:
    from starlette.requests import Request

    from arvel.auth.auth_service import AuthService
    from arvel.auth.email_verification_service import EmailVerificationService
    from arvel.auth.password_service import PasswordService
    from arvel.http.ratelimit import RateLimiterStore


@dataclass
class CookieConfig:
    """Cookie and controller settings for :class:`AuthController`."""

    refresh_cookie: str = "__Host-refresh"
    csrf_cookie: str = "_csrf"
    refresh_ttl_seconds: int = field(default=14 * 24 * 3600)
    secure: bool = True
    user_resource_class: type[Any] | None = None
    verify_redirect_url: str | None = None


class AuthController(Controller):
    """Thin façade between the HTTP layer and the auth services.

    Pass ``config.user_resource_class`` to replace the default
    :class:`UserResource` with an app-specific subclass that adds extra fields
    (e.g. ``theme``, ``suspended_at``). The class must be a Pydantic model with
    ``from_attributes=True`` so ``model_validate(orm_user)`` works.
    """

    def __init__(
        self,
        *,
        auth: AuthService,
        passwords: PasswordService,
        email_verification: EmailVerificationService,
        cookies: CookieConfig | None = None,
    ) -> None:
        self._auth = auth
        self._passwords = passwords
        self._email_verification = email_verification
        cfg = cookies or CookieConfig()
        self._refresh_cookie = cfg.refresh_cookie
        self._csrf_cookie = cfg.csrf_cookie
        self._refresh_ttl_seconds = cfg.refresh_ttl_seconds
        self._cookie_secure = cfg.secure
        self._user_resource_cls: type[Any] = cfg.user_resource_class or UserResource
        self._verify_redirect_url = cfg.verify_redirect_url
        self._resend_store: RateLimiterStore | None = None

    # ─── Register ──────────────────────────────────────────────────────────

    async def register(
        self,
        payload: RegisterRequest,
    ) -> AuthEnvelope[UserResource]:
        """``POST /auth/register`` — create a user and queue a verification email."""
        try:
            user = await self._auth.register(
                name=payload.name,
                email=str(payload.email),
                password=payload.password,
                locale=payload.locale,
            )
        except EmailAlreadyRegisteredError as exc:
            raise ConflictException("Email already registered.") from exc
        return AuthEnvelope(data=self._user_resource_cls.model_validate(user))

    # ─── Login ─────────────────────────────────────────────────────────────

    async def login(
        self,
        payload: LoginRequest,
        response: Response,
    ) -> LoginResponse:
        """``POST /auth/login`` — issue JWT + set refresh/CSRF cookie pair."""
        try:
            user, tokens = await self._auth.login(
                email=str(payload.email), password=payload.password
            )
        except EmailNotVerifiedError as exc:
            raise ValidationException("Email not verified.") from exc
        except AccountSuspendedError as exc:
            raise AuthorizationException("Account suspended.") from exc
        except InvalidCredentialsError as exc:
            raise UnauthenticatedException("Invalid credentials.") from exc

        del user  # returned via cookie + access token, not the response body
        self._set_auth_cookies(
            response,
            refresh_token=tokens.refresh_token,
            csrf_token=tokens.csrf_token,
        )
        return LoginResponse(
            access_token=tokens.access_token,
            expires_in=tokens.expires_in,
        )

    # ─── Refresh ───────────────────────────────────────────────────────────

    async def refresh(self, request: Request, response: Response) -> LoginResponse:
        """``POST /auth/refresh`` — rotate refresh token and mint a new access JWT."""
        cookie = request.cookies.get(self._refresh_cookie)
        if not cookie:
            raise UnauthenticatedException("Refresh cookie missing.")
        try:
            _user, tokens = await self._auth.refresh(refresh_token=cookie)
        except (InvalidCredentialsError, TokenReuseDetectedError) as exc:
            self._clear_auth_cookies(response)
            raise UnauthenticatedException("Refresh token invalid.") from exc

        self._set_auth_cookies(
            response,
            refresh_token=tokens.refresh_token,
            csrf_token=tokens.csrf_token,
        )
        return LoginResponse(
            access_token=tokens.access_token,
            expires_in=tokens.expires_in,
        )

    # ─── Logout ────────────────────────────────────────────────────────────

    async def logout(self, request: Request, response: Response) -> Response:
        """``POST /auth/logout`` — revoke refresh + access token, clear cookies. Always 204."""
        cookie = request.cookies.get(self._refresh_cookie)
        await self._auth.logout(refresh_token=cookie, access_token=_extract_bearer(request))
        self._clear_auth_cookies(response)
        return JSONResponse(status_code=204, content=None)

    # ─── Me ────────────────────────────────────────────────────────────────

    async def me(self, request: Request) -> AuthEnvelope[UserResource]:
        """``GET /auth/me`` — return the user identified by the bearer JWT."""
        token = _extract_bearer(request)
        if token is None:
            raise UnauthenticatedException("Bearer token missing.")
        try:
            user = await self._auth.me(access_token=token)
        except InvalidCredentialsError as exc:
            raise UnauthenticatedException("Invalid bearer token.") from exc
        except AccountSuspendedError as exc:
            raise AuthorizationException("Account suspended.") from exc
        return AuthEnvelope(data=self._user_resource_cls.model_validate(user))

    # ─── Forgot password ───────────────────────────────────────────────────

    async def forgot_password(
        self,
        payload: ForgotPasswordRequest,
    ) -> dict[str, str]:
        """``POST /auth/forgot-password`` — always 202; hides whether email exists."""
        await self._passwords.forgot(str(payload.email).strip().lower())
        return {"status": "queued"}

    # ─── Reset password ────────────────────────────────────────────────────

    async def reset_password(
        self,
        payload: ResetPasswordRequest,
    ) -> dict[str, str]:
        """``POST /auth/reset-password`` — verify token, update password, revoke sessions."""
        try:
            await self._passwords.reset(
                token=payload.token,
                password=payload.password,
            )
        except PasswordResetTokenInvalidError as exc:
            raise ValidationException(
                "Reset token is invalid or has expired.",
                details=[{"field": "token", "issue": "Reset token is invalid or has expired."}],
            ) from exc
        return {"status": "reset"}

    # ─── Verify email ──────────────────────────────────────────────────────

    async def verify_email(self, signed: str) -> Response:
        """``GET /auth/verify/{signed}`` — consume a signed verification URL.

        Redirects to ``verify_redirect_url`` when configured; otherwise
        returns a JSON ``{"status": "verified"}`` body.
        """
        try:
            await self._email_verification.consume(signed)
        except EmailVerificationInvalidError as exc:
            raise UnauthenticatedException("Verification link is invalid or expired.") from exc
        if self._verify_redirect_url:
            return RedirectResponse(url=self._verify_redirect_url, status_code=302)
        return JSONResponse({"status": "verified"})

    async def verify_email_resend(
        self,
        payload: ResendVerificationRequest,
    ) -> dict[str, str]:
        """``POST /auth/verify/resend`` — re-issue a verification email.

        Public and email-based: unverified accounts can't obtain a JWT, so this
        can't be bearer-gated. Throttled per email (once per 60 s) and always
        answered with a uniform 202, so callers can't probe which emails exist.
        """
        from arvel.http.exceptions import ThrottleException  # noqa: PLC0415

        email = str(payload.email).strip().lower()
        if self._resend_store is None:
            # Cache-backed so the resend limit holds across workers (Redis in
            # prod); degrades to per-process only when the cache itself is.
            from arvel.http.ratelimit import CacheStore  # noqa: PLC0415

            self._resend_store = CacheStore()

        attempt = await self._resend_store.hit(f"resend:{email}", decay_seconds=60)
        if attempt.count > 1:
            raise ThrottleException("Too many resend requests.", retry_after_seconds=60)

        signed = await self._email_verification.issue_for_email(email)
        if signed is not None:
            await self._dispatch_verification_email(email=email, signed=signed)
        return {"status": "queued"}

    # ─── mail helpers ──────────────────────────────────────────────────────

    async def _dispatch_verification_email(self, *, email: str, signed: str) -> None:
        """Queue a verification email — no-op when mail is not configured."""
        try:
            from arvel.auth.mail import VerifyEmailMailable  # noqa: PLC0415
            from arvel.config import config  # noqa: PLC0415
            from arvel.facades.mail import Mail  # noqa: PLC0415

            # Build the clickable link the same way SendVerificationEmail does —
            # the mailable templates verify_url verbatim, so it must be a real URL,
            # not the raw signed blob.
            app_url = config("app.url", "http://localhost:8000")
            verify_url = self._email_verification.build_url(
                base_url=f"{app_url}/api/auth/verify",
                signed=signed,
            )
            mailable = VerifyEmailMailable(user_email=email, verify_url=verify_url)
            await Mail.to(email).send(mailable)
        except Exception:  # noqa: BLE001
            import logging  # noqa: PLC0415

            logging.getLogger(__name__).warning(
                "verify_email_resend: mail send failed for %s", email, exc_info=True
            )

    # ─── cookie helpers ────────────────────────────────────────────────────

    def _set_auth_cookies(
        self,
        response: Response,
        *,
        refresh_token: str,
        csrf_token: str,
    ) -> None:
        response.set_cookie(
            key=self._refresh_cookie,
            value=refresh_token,
            max_age=self._refresh_ttl_seconds,
            httponly=True,
            secure=self._cookie_secure,
            samesite="strict",
            path="/",
        )
        response.set_cookie(
            key=self._csrf_cookie,
            value=csrf_token,
            max_age=self._refresh_ttl_seconds,
            httponly=False,
            secure=self._cookie_secure,
            samesite="strict",
            path="/",
        )

    def _clear_auth_cookies(self, response: Response) -> None:
        response.delete_cookie(
            key=self._refresh_cookie,
            path="/",
            samesite="strict",
            secure=self._cookie_secure,
        )
        response.delete_cookie(
            key=self._csrf_cookie,
            path="/",
            samesite="strict",
            secure=self._cookie_secure,
        )


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    prefix, _, token = header.partition(" ")
    if prefix.lower() != "bearer" or not token:
        return None
    return token.strip()


__all__ = ["AuthController"]
