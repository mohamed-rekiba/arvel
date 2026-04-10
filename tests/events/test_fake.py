"""Tests for EventFake testing double — NFR-004.

NFR-004: All contracts have testing fakes.
"""

from __future__ import annotations

from .conftest import OrderPlaced, UserRegistered


class TestEventFake:
    """NFR-004: EventFake captures dispatched events for assertions."""

    async def test_fake_records_dispatched_events(self) -> None:
        from arvel.events.fake import EventFake

        fake = EventFake()
        event = UserRegistered(user_id="u1", email="a@b.com")
        await fake.dispatch(event)

        assert fake.dispatched_count == 1

    async def test_fake_assert_dispatched(self) -> None:
        from arvel.events.fake import EventFake

        fake = EventFake()
        await fake.dispatch(UserRegistered(user_id="u1", email="a@b.com"))

        fake.assert_dispatched(UserRegistered)

    async def test_fake_assert_dispatched_count(self) -> None:
        from arvel.events.fake import EventFake

        fake = EventFake()
        await fake.dispatch(UserRegistered(user_id="u1", email="a@b.com"))
        await fake.dispatch(UserRegistered(user_id="u2", email="b@c.com"))

        assert fake.dispatched_count == 2

    async def test_fake_assert_not_dispatched(self) -> None:
        from arvel.events.fake import EventFake

        fake = EventFake()
        await fake.dispatch(UserRegistered(user_id="u1", email="a@b.com"))

        fake.assert_not_dispatched(OrderPlaced)

    async def test_fake_assert_nothing_dispatched(self) -> None:
        from arvel.events.fake import EventFake

        fake = EventFake()
        fake.assert_nothing_dispatched()
