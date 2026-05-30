"""Access + refresh token pair returned from login and refresh endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TokenPair(BaseModel):
    """Laravel-style token response: short-lived access JWT + rotatable refresh token.

    ``csrf_token`` is a random 32-byte URL-safe value that the controller
    stores in a readable ``_csrf`` cookie. The SPA echoes it back via
    ``X-CSRF-TOKEN`` on every state-changing request so the CSRF double-submit
    middleware can verify it without server-side session storage.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    access_token: str
    refresh_token: str
    csrf_token: str
    token_type: str = Field(default="Bearer")
    expires_in: int = Field(description="Access token lifetime in seconds", ge=1)
