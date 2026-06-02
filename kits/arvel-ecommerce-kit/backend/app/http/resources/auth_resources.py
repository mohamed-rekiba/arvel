"""Auth response models for the e-commerce kit.

``EcommerceUserResource`` is the JWT /me payload. Sensitive fields (password)
are excluded by construction. ``from_attributes=True`` lets auth guards call
``EcommerceUserResource.model_validate(orm_instance)`` directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from arvel.auth.http.resources import AuthEnvelope, LoginResponse
from pydantic import BaseModel, ConfigDict


class EcommerceUserResource(BaseModel):
    """User payload for the SPA /me endpoint and JWT subject claims."""

    model_config = ConfigDict(from_attributes=True, frozen=True, extra="ignore")

    id: int
    email: str
    name: str
    locale: str = "en"
    theme: Literal["light", "dark", "system"] = "system"
    email_verified_at: datetime | None = None
    suspended_at: datetime | None = None
    created_at: datetime | None = None


__all__ = [
    "AuthEnvelope",
    "EcommerceUserResource",
    "LoginResponse",
]
