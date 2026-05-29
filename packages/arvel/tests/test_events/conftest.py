"""Shared fixtures for events tests."""

from __future__ import annotations

import pytest
from arvel.events.event import Event


class UserRegistered(Event):
    user_id: int
    email: str


class OrderShipped(Event):
    order_id: int


@pytest.fixture
def user_registered() -> UserRegistered:
    return UserRegistered(user_id=1, email="alice@example.com")


@pytest.fixture
def order_shipped() -> OrderShipped:
    return OrderShipped(order_id=99)
