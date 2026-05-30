"""FR-013-009 — ShouldBroadcast mixin."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from pydantic import BaseModel


def test_should_broadcast_isinstance_check() -> None:
    """FR-013-009 AC1: isinstance(event, ShouldBroadcast) is True for mixed-in events."""
    from arvel.broadcasting import ShouldBroadcast
    from arvel.events.event import Event

    class _Evt(Event, ShouldBroadcast):
        def broadcast_on(self) -> Sequence[str]:
            return ["x"]

    assert isinstance(_Evt(), ShouldBroadcast)


def test_default_broadcast_as_is_class_name() -> None:
    """FR-013-009 AC2: default broadcast_as returns class name."""
    from arvel.broadcasting import ShouldBroadcast
    from arvel.events.event import Event

    class OrderShipped(Event, ShouldBroadcast):
        def broadcast_on(self) -> Sequence[str]:
            return ["x"]

    assert OrderShipped().broadcast_as() == "OrderShipped"


def test_default_broadcast_with_returns_model_dump_for_basemodel() -> None:
    """FR-013-009 AC3: broadcast_with defaults to model_dump() for BaseModel events."""
    from arvel.broadcasting import ShouldBroadcast
    from arvel.events.event import Event

    class OrderShipped(Event, ShouldBroadcast):
        order_id: int = 0

        def broadcast_on(self) -> Sequence[str]:
            return ["x"]

    assert OrderShipped(order_id=42).broadcast_with() == {"order_id": 42}


def test_broadcast_on_without_override_raises() -> None:
    """Mixin alone (no broadcast_on override) raises NotImplementedError when called."""
    from arvel.broadcasting import ShouldBroadcast

    class _Bad(BaseModel, ShouldBroadcast):
        pass

    with pytest.raises(NotImplementedError):
        _Bad().broadcast_on()
