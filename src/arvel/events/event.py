"""Event base class — all domain events inherit from this."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class Event(BaseModel):
    """Base class for domain events.

    Events are immutable Pydantic models. Subclass and add fields for
    your domain-specific payload. Sensitive fields should use
    ``exclude=True`` in their Field definition to prevent queue serialization.
    """

    model_config = ConfigDict(frozen=True)

    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
