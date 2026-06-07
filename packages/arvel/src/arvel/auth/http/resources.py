"""HTTP response models for the auth layer.

``UserResource``, ``LoginResponse``, and ``AuthEnvelope`` live here so
the controller stays free of ad-hoc ``dict`` construction.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

T = TypeVar("T")


def _stringify_id(value: object) -> str:
    return str(value)


# IDs travel as strings in the API even when the model stores them as ints or
# UUIDs (see the API design rule). Coerce at the boundary so apps with integer
# primary keys serialise cleanly.
UserId = Annotated[str, BeforeValidator(_stringify_id)]


class UserResource(BaseModel):
    """Serialised view of a ``User`` model sent to the client.

    ``model_config`` uses ``from_attributes=True`` so ``model_validate(user_orm_row)``
    works without an explicit ``model_dump()`` call on the ORM instance.
    Sensitive fields (``password``) are never declared here — they're absent
    by construction.
    """

    model_config = ConfigDict(from_attributes=True, frozen=True, extra="ignore")

    id: UserId
    name: str
    email: str
    locale: str | None = None
    email_verified_at: datetime | None = None
    created_at: datetime | None = None


class LoginResponse(BaseModel):
    """OAuth-compatible token response body for ``login`` and ``refresh``.

    ``refresh_token`` and ``csrf_token`` travel as HttpOnly / readable
    cookies respectively, not in this body — this shape is intentionally
    minimal to reduce the risk of a JS script accidentally logging the
    refresh token.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    access_token: str
    token_type: str = Field(default="bearer")
    expires_in: int = Field(description="Access token lifetime in seconds", ge=1)


class AuthEnvelope(BaseModel, Generic[T]):
    """``{"data": <resource>}`` wrapper returned by ``register``, ``me``.

    The generic parameter ``T`` is the resource type (e.g. ``UserResource``).
    Pydantic serialises it correctly because ``model_config`` allows arbitrary
    types and ``from_attributes=True`` propagates to nested models.
    """

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    data: T


__all__ = [
    "AuthEnvelope",
    "LoginResponse",
    "UserResource",
]
