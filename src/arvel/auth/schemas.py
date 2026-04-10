"""Auth request/response schemas — Pydantic models for validation."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field  # noqa: TC002


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=72)


class VerifyEmailRequest(BaseModel):
    token: str


class MessageResponse(BaseModel):
    message: str
