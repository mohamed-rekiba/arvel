"""Tests for Event base class."""

from __future__ import annotations

import pytest
from arvel.events.event import Event, EventRegistry


class SimpleEvent(Event):
    value: str


class TestEvent:
    """Event is a Pydantic BaseModel."""

    def test_event_is_pydantic_model(self) -> None:
        from pydantic import BaseModel

        assert issubclass(Event, BaseModel)

    def test_subclass_has_typed_fields(self) -> None:
        evt = SimpleEvent(value="hello")
        assert evt.value == "hello"

    def test_event_serializes_to_json(self) -> None:
        evt = SimpleEvent(value="hello")
        json_str = evt.model_dump_json()
        assert '"value"' in json_str
        assert '"hello"' in json_str

    def test_event_deserializes_from_json(self) -> None:
        evt = SimpleEvent(value="world")
        restored = SimpleEvent.model_validate_json(evt.model_dump_json())
        assert restored.value == evt.value

    def test_event_auto_registers_in_event_registry(self) -> None:
        key = f"{SimpleEvent.__module__}.{SimpleEvent.__qualname__}"
        assert key in EventRegistry
        assert EventRegistry[key] is SimpleEvent

    def test_invalid_field_raises_validation_error(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SimpleEvent.model_validate({"value": 123})
