"""Tests for channel types — FR-004.

FR-004: Channel, PrivateChannel, PresenceChannel as frozen dataclasses.
"""

from __future__ import annotations

import pytest

from arvel.broadcasting.channels import Channel, PresenceChannel, PrivateChannel


class TestChannelTypes:
    """FR-004: Three channel types with correct inheritance."""

    def test_public_channel_has_name(self) -> None:
        ch = Channel("news")
        assert ch.name == "news"

    def test_public_channel_is_frozen(self) -> None:
        ch = Channel("news")
        with pytest.raises(AttributeError):
            ch.name = "other"  # ty: ignore[invalid-assignment]

    def test_private_channel_is_channel_subclass(self) -> None:
        ch = PrivateChannel("orders.42")
        assert isinstance(ch, Channel)
        assert ch.name == "orders.42"

    def test_presence_channel_is_channel_subclass(self) -> None:
        ch = PresenceChannel("chat.1")
        assert isinstance(ch, Channel)
        assert ch.name == "chat.1"

    def test_channel_equality(self) -> None:
        assert Channel("news") == Channel("news")
        assert Channel("news") != Channel("other")

    def test_private_channel_not_equal_to_public(self) -> None:
        assert PrivateChannel("x") != Channel("x")

    def test_presence_channel_not_equal_to_private(self) -> None:
        assert PresenceChannel("x") != PrivateChannel("x")
