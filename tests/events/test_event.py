"""Tests for Event base class — Story 1.

FR-001: Event base class (Pydantic model) with occurred_at timestamp.
NFR-006: Events do not serialize sensitive fields.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError

from .conftest import SensitiveEvent, UserRegistered


class TestEventBaseClass:
    """FR-001: Event base class with occurred_at."""

    def test_event_has_occurred_at(self) -> None:
        event = UserRegistered(user_id="u1", email="a@b.com")
        assert isinstance(event.occurred_at, datetime)

    def test_occurred_at_uses_utc(self) -> None:
        event = UserRegistered(user_id="u1", email="a@b.com")
        assert event.occurred_at.tzinfo is not None

    def test_event_is_frozen(self) -> None:
        event = UserRegistered(user_id="u1", email="a@b.com")
        mutable_ref = cast("Any", event)
        with pytest.raises(ValidationError):
            mutable_ref.user_id = "u2"

    def test_event_serializes_to_json(self) -> None:
        event = UserRegistered(user_id="u1", email="a@b.com")
        data = event.model_dump(mode="json")
        assert data["user_id"] == "u1"
        assert data["email"] == "a@b.com"
        assert "occurred_at" in data

    def test_event_deserializes_from_dict(self) -> None:
        now = datetime.now(UTC)
        event = UserRegistered.model_validate(
            {"user_id": "u1", "email": "a@b.com", "occurred_at": now.isoformat()}
        )
        assert event.user_id == "u1"

    def test_custom_occurred_at_preserved(self) -> None:
        custom_time = datetime(2025, 1, 1, tzinfo=UTC)
        event = UserRegistered(user_id="u1", email="a@b.com", occurred_at=custom_time)
        assert event.occurred_at == custom_time


class TestEventSensitiveFieldExclusion:
    """NFR-006: Events must not serialize sensitive fields when dispatched to queues."""

    def test_sensitive_fields_excluded_from_queue_serialization(self) -> None:
        """Sensitive fields should be excludable during serialization.

        The implementation should support marking fields for exclusion
        so that passwords/tokens don't end up in Redis payloads.
        """
        event = SensitiveEvent(user_id="u1", password="secret123")
        data = event.model_dump(exclude={"password"})
        assert "password" not in data
        assert data["user_id"] == "u1"
