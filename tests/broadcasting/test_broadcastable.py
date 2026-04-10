"""Tests for Broadcastable protocol and BroadcastEventListener — FR-007, FR-008.

FR-007: Broadcastable protocol for events.
FR-008: BroadcastEventListener auto-broadcasts broadcastable events.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.broadcasting.broadcastable import Broadcastable
from arvel.broadcasting.channels import PrivateChannel
from arvel.events.event import Event

if TYPE_CHECKING:
    from arvel.broadcasting.channels import Channel


class ShippedEvent(Event):
    """Test broadcastable event."""

    order_id: int

    def broadcast_on(self) -> list[Channel]:
        return [PrivateChannel(f"orders.{self.order_id}")]

    def broadcast_as(self) -> str:
        return "order.shipped"

    def broadcast_with(self) -> dict[str, Any]:
        return {"order_id": self.order_id}


class PlainEvent(Event):
    """Test event that does NOT implement Broadcastable."""

    message: str


class TestBroadcastableProtocol:
    """FR-007: Events implement Broadcastable to opt into broadcasting."""

    def test_event_with_broadcastable_is_recognized(self) -> None:
        event = ShippedEvent(order_id=42)
        assert isinstance(event, Broadcastable)

    def test_event_without_broadcastable_is_not_recognized(self) -> None:
        event = PlainEvent(message="hello")
        assert not isinstance(event, Broadcastable)

    def test_broadcast_on_returns_channels(self) -> None:
        event = ShippedEvent(order_id=42)
        channels = event.broadcast_on()
        assert len(channels) == 1
        assert channels[0].name == "orders.42"
        assert isinstance(channels[0], PrivateChannel)

    def test_broadcast_as_returns_event_name(self) -> None:
        event = ShippedEvent(order_id=42)
        assert event.broadcast_as() == "order.shipped"

    def test_broadcast_with_returns_data(self) -> None:
        event = ShippedEvent(order_id=42)
        assert event.broadcast_with() == {"order_id": 42}


class TestBroadcastEventListener:
    """FR-008: Listener auto-broadcasts broadcastable events."""

    async def test_listener_broadcasts_broadcastable_event(self) -> None:
        from arvel.broadcasting.fake import BroadcastFake
        from arvel.broadcasting.listener import BroadcastEventListener

        fake = BroadcastFake()
        listener = BroadcastEventListener(broadcaster=fake)

        event = ShippedEvent(order_id=42)
        await listener.handle(event)

        fake.assert_broadcast("order.shipped", channel="orders.42")

    async def test_listener_ignores_non_broadcastable_event(self) -> None:
        from arvel.broadcasting.fake import BroadcastFake
        from arvel.broadcasting.listener import BroadcastEventListener

        fake = BroadcastFake()
        listener = BroadcastEventListener(broadcaster=fake)

        event = PlainEvent(message="hello")
        await listener.handle(event)

        fake.assert_nothing_broadcast()
