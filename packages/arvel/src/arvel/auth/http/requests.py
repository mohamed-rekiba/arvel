"""Pydantic request models for the auth HTTP layer.

Apps can use these directly or subclass them to add app-specific validation.
A future ``request_classes`` parameter on :func:`register_auth_routes` will
let apps swap the defaults; until then, subclass and re-register manually.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class RegisterRequest(BaseModel):
    """``POST /auth/register`` body."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    password_confirmation: str = Field(min_length=8, max_length=128)
    locale: str | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def passwords_match(self) -> RegisterRequest:
        if self.password != self.password_confirmation:
            msg = "password and password_confirmation do not match"
            raise ValueError(msg)
        return self


class LoginRequest(BaseModel):
    """``POST /auth/login`` body."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordRequest(BaseModel):
    """``POST /auth/forgot-password`` body."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """``POST /auth/reset-password`` body."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    token: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)
    password_confirmation: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self) -> ResetPasswordRequest:
        if self.password != self.password_confirmation:
            msg = "password and password_confirmation do not match"
            raise ValueError(msg)
        return self


class ResendVerificationRequest(BaseModel):
    """``POST /auth/verify/resend`` body — empty; auth from bearer."""

    model_config = ConfigDict(frozen=True, extra="forbid")


__all__ = [
    "ForgotPasswordRequest",
    "LoginRequest",
    "RegisterRequest",
    "ResendVerificationRequest",
    "ResetPasswordRequest",
]
