"""Shared fixtures for broadcasting tests."""

from __future__ import annotations

from typing import Any

import pytest

from arvel.broadcasting.channels import Channel, PresenceChannel, PrivateChannel
from arvel.events.event import Event


class OrderShipped(Event):
    """Test event that implements Broadcastable."""

    order_id: int
    tracking_url: str = "https://track.example.com/123"


class UserJoined(Event):
    """Another test event for counting/filtering."""

    user_id: str
    room_id: int


@pytest.fixture
def public_channel() -> Channel:
    return Channel("news")


@pytest.fixture
def private_channel() -> PrivateChannel:
    return PrivateChannel("orders.42")


@pytest.fixture
def presence_channel() -> PresenceChannel:
    return PresenceChannel("chat.1")


@pytest.fixture
def sample_data() -> dict[str, Any]:
    return {"order_id": 42, "tracking_url": "https://track.example.com/123"}
