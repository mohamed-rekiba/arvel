"""Tests for BroadcastFake — FR-009.

FR-009: BroadcastFake captures broadcasts with assertion helpers.
"""

from __future__ import annotations

import pytest

from arvel.broadcasting.channels import Channel, PrivateChannel


class TestBroadcastFake:
    """FR-009: Fake captures broadcasts for test assertions."""

    async def test_fake_records_broadcast(self) -> None:
        from arvel.broadcasting.fake import BroadcastFake

        fake = BroadcastFake()
        await fake.broadcast([Channel("news")], "article.published", {"id": 1})

        assert fake.broadcast_count == 1

    async def test_assert_broadcast_by_event_name(self) -> None:
        from arvel.broadcasting.fake import BroadcastFake

        fake = BroadcastFake()
        await fake.broadcast([Channel("news")], "article.published", {"id": 1})

        fake.assert_broadcast("article.published")

    async def test_assert_broadcast_with_channel_filter(self) -> None:
        from arvel.broadcasting.fake import BroadcastFake

        fake = BroadcastFake()
        await fake.broadcast([PrivateChannel("orders.42")], "order.shipped", {"id": 42})

        fake.assert_broadcast("order.shipped", channel="orders.42")

    async def test_assert_broadcast_fails_when_not_found(self) -> None:
        from arvel.broadcasting.fake import BroadcastFake

        fake = BroadcastFake()

        with pytest.raises(AssertionError, match="never broadcast"):
            fake.assert_broadcast("order.shipped")

    async def test_assert_broadcast_on_channel(self) -> None:
        from arvel.broadcasting.fake import BroadcastFake

        fake = BroadcastFake()
        await fake.broadcast([Channel("news")], "test", {})

        fake.assert_broadcast_on("news")

    async def test_assert_broadcast_on_channel_fails(self) -> None:
        from arvel.broadcasting.fake import BroadcastFake

        fake = BroadcastFake()

        with pytest.raises(AssertionError, match="No broadcast"):
            fake.assert_broadcast_on("orders.42")

    async def test_assert_nothing_broadcast(self) -> None:
        from arvel.broadcasting.fake import BroadcastFake

        fake = BroadcastFake()
        fake.assert_nothing_broadcast()

    async def test_assert_nothing_broadcast_fails(self) -> None:
        from arvel.broadcasting.fake import BroadcastFake

        fake = BroadcastFake()
        await fake.broadcast([Channel("news")], "test", {})

        with pytest.raises(AssertionError, match="Expected no broadcasts"):
            fake.assert_nothing_broadcast()

    async def test_assert_broadcast_count(self) -> None:
        from arvel.broadcasting.fake import BroadcastFake

        fake = BroadcastFake()
        await fake.broadcast([Channel("a")], "e1", {})
        await fake.broadcast([Channel("b")], "e1", {})
        await fake.broadcast([Channel("c")], "e2", {})

        fake.assert_broadcast_count("e1", 2)

    async def test_assert_broadcast_count_fails_on_mismatch(self) -> None:
        from arvel.broadcasting.fake import BroadcastFake

        fake = BroadcastFake()
        await fake.broadcast([Channel("a")], "e1", {})

        with pytest.raises(AssertionError, match="Expected 3"):
            fake.assert_broadcast_count("e1", 3)

    async def test_fake_is_broadcast_contract(self) -> None:
        from arvel.broadcasting.contracts import BroadcastContract
        from arvel.broadcasting.fake import BroadcastFake

        assert isinstance(BroadcastFake(), BroadcastContract)
