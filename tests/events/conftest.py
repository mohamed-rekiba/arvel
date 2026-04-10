"""Shared fixtures for the arvel.events test suite."""

from __future__ import annotations

from typing import ClassVar

import pytest

from arvel.events.event import Event
from arvel.events.listener import Listener, queued

# ──── Test Events ────


class UserRegistered(Event):
    user_id: str
    email: str


class OrderPlaced(Event):
    order_id: str
    total: float


class SensitiveEvent(Event):
    """Event with a field that should not be serialized to the queue."""

    user_id: str
    password: str  # must be excluded during queue serialization


# ──── Test Listeners ────


class SendWelcomeEmail(Listener):
    """Sync listener for UserRegistered."""

    calls: ClassVar[list[Event]] = []

    async def handle(self, event: UserRegistered) -> None:
        self.calls.append(event)


class LogRegistration(Listener):
    """Another sync listener for UserRegistered (priority testing)."""

    calls: ClassVar[list[Event]] = []

    async def handle(self, event: UserRegistered) -> None:
        self.calls.append(event)


@queued
class SendWelcomeEmailQueued(Listener):
    """Queued listener for UserRegistered."""

    async def handle(self, event: UserRegistered) -> None:
        pass


class OrderConfirmation(Listener):
    """Sync listener for OrderPlaced."""

    calls: ClassVar[list[Event]] = []

    async def handle(self, event: OrderPlaced) -> None:
        self.calls.append(event)


# ──── Fixtures ────


@pytest.fixture
def user_registered_event() -> UserRegistered:
    return UserRegistered(user_id="usr_001", email="test@example.com")


@pytest.fixture
def order_placed_event() -> OrderPlaced:
    return OrderPlaced(order_id="ord_001", total=99.99)
