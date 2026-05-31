"""Provider-agnostic OAuth data transfer objects."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OAuthToken(BaseModel):
    """A token set returned from an authorization-code exchange."""

    model_config = ConfigDict(frozen=True)

    access_token: str
    # "Bearer" is the OAuth token type literal, not a secret.
    token_type: str = "Bearer"  # noqa: S105
    expires_in: int | None = None
    refresh_token: str | None = None
    id_token: str | None = None
    scope: str | None = None
    raw: dict[str, object] = Field(default_factory=dict)


class OAuthUser(BaseModel):
    """A normalized identity resolved from a provider."""

    model_config = ConfigDict(frozen=True)

    provider: str
    provider_id: str
    email: str | None = None
    # Providers vary: only trust the email when explicitly verified upstream.
    email_verified: bool = False
    name: str | None = None
    avatar: str | None = None
    raw: dict[str, object] = Field(default_factory=dict)


__all__ = ["OAuthToken", "OAuthUser"]
