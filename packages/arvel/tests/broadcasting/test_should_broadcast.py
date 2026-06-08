"""ShouldBroadcast mixin."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from pydantic import BaseModel


def test_should_broadcast_isinstance_check() -> None:
    """isinstance(event, ShouldBroadcast) is True for mixed-in events."""
    from arvel.broadcasting import ShouldBroadcast
    from arvel.events.event import Event

    class _Evt(Event, ShouldBroadcast):
        def broadcast_on(self) -> Sequence[str]:
            return ["x"]

    assert isinstance(_Evt(), ShouldBroadcast)


def test_default_broadcast_as_is_class_name() -> None:
    """default broadcast_as returns class name."""
    from arvel.broadcasting import ShouldBroadcast
    from arvel.events.event import Event

    class OrderShipped(Event, ShouldBroadcast):
        def broadcast_on(self) -> Sequence[str]:
            return ["x"]

    assert OrderShipped().broadcast_as() == "OrderShipped"


def test_default_broadcast_with_returns_model_dump_for_basemodel() -> None:
    """broadcast_with defaults to model_dump for BaseModel events."""
    from arvel.broadcasting import ShouldBroadcast
    from arvel.events.event import Event

    class OrderShipped(Event, ShouldBroadcast):
        order_id: int = 0

        def broadcast_on(self) -> Sequence[str]:
            return ["x"]

    assert OrderShipped(order_id=42).broadcast_with() == {"order_id": 42}


def test_broadcast_with_is_json_safe_for_rich_types() -> None:
    """datetime/UUID/Decimal fields serialize to JSON-safe values, so drivers can
    json.dumps the payload without blowing up."""
    import json
    from datetime import UTC, datetime
    from decimal import Decimal
    from uuid import UUID, uuid4

    from arvel.broadcasting import ShouldBroadcast
    from arvel.events.event import Event

    class OrderShipped(Event, ShouldBroadcast):
        order_id: UUID
        total: Decimal
        shipped_at: datetime

        def broadcast_on(self) -> Sequence[str]:
            return ["orders"]

    oid = uuid4()
    payload = OrderShipped(
        order_id=oid,
        total=Decimal("19.99"),
        shipped_at=datetime(2026, 1, 1, tzinfo=UTC),
    ).broadcast_with()

    assert payload["order_id"] == str(oid)
    assert payload["total"] == "19.99"
    assert payload["shipped_at"] == "2026-01-01T00:00:00Z"
    # The whole point: this must not raise.
    json.dumps(dict(payload))


def test_broadcast_on_without_override_raises() -> None:
    """Mixin alone (no broadcast_on override) raises NotImplementedError when called."""
    from arvel.broadcasting import ShouldBroadcast

    class _Bad(BaseModel, ShouldBroadcast):
        pass

    with pytest.raises(NotImplementedError):
        _Bad().broadcast_on()
