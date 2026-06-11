"""Authentication — services, models, tokens, events, and HTTP layer.

Public surface for ``arvel.auth``. Apps import everything they need from
this module; sub-packages are an implementation detail.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from arvel.auth.auth_service import AuthService, get_auth_service
from arvel.auth.email_verification_service import EmailVerificationService
from arvel.auth.events import (
    AuthEvent,
    EmailVerified,
    LoggedIn,
    LoggedOut,
    LoginFailed,
    PasswordResetCompleted,
    PasswordResetRequested,
    Registered,
    TokenReuseDetected,
)
from arvel.auth.exceptions import (
    AccountSuspendedError,
    AuthConfigError,
    AuthError,
    AuthorizationException,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    EmailVerificationInvalidError,
    InvalidCredentialsError,
    PasswordResetTokenInvalidError,
    TokenReuseDetectedError,
    UnauthenticatedException,
)
from arvel.auth.guard import Guard, UserResolver
from arvel.auth.guards.jwt import JwtGuard
from arvel.auth.guards.session import SessionGuard
from arvel.auth.guards.token import TokenGuard
from arvel.auth.http.controller import AuthController
from arvel.auth.http.routes import register_auth_routes
from arvel.auth.models import RefreshToken
from arvel.auth.password_service import PasswordService
from arvel.auth.refresh_tokens import (
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expires_at,
)
from arvel.auth.repositories import ArventTokenRepository, MorphUserRepository
from arvel.auth.token_pair import TokenPair

if TYPE_CHECKING:
    from arvel.auth.models.password_reset import PasswordReset
    from arvel.auth.models.personal_access_token import PersonalAccessToken
    from arvel.auth.models.user import User


def __getattr__(name: str) -> object:
    if name == "User":
        from arvel.auth.models.user import User  # noqa: PLC0415

        return User
    if name == "PasswordReset":
        from arvel.auth.models.password_reset import PasswordReset  # noqa: PLC0415

        return PasswordReset
    if name == "PersonalAccessToken":
        from arvel.auth.models.personal_access_token import PersonalAccessToken  # noqa: PLC0415

        return PersonalAccessToken
    msg = f"module 'arvel.auth' has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = [
    "AccountSuspendedError",
    "ArventTokenRepository",
    "AuthConfigError",
    "AuthController",
    "AuthError",
    "AuthEvent",
    "AuthService",
    "AuthorizationException",
    "EmailAlreadyRegisteredError",
    "EmailNotVerifiedError",
    "EmailVerificationInvalidError",
    "EmailVerificationService",
    "EmailVerified",
    "Guard",
    "InvalidCredentialsError",
    "JwtGuard",
    "LoggedIn",
    "LoggedOut",
    "LoginFailed",
    "MorphUserRepository",
    "PasswordReset",
    "PasswordResetCompleted",
    "PasswordResetRequested",
    "PasswordResetTokenInvalidError",
    "PasswordService",
    "PersonalAccessToken",
    "RefreshToken",
    "Registered",
    "SessionGuard",
    "TokenGuard",
    "TokenPair",
    "TokenReuseDetected",
    "TokenReuseDetectedError",
    "UnauthenticatedException",
    "User",
    "UserResolver",
    "generate_refresh_token",
    "get_auth_service",
    "hash_refresh_token",
    "refresh_token_expires_at",
    "register_auth_routes",
]
