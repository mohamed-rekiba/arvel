"""Tests for QueueFake testing double — NFR-004.

NFR-004: All contracts have testing fakes.
"""

from __future__ import annotations

from .conftest import SendEmailJob


class TestQueueFake:
    """NFR-004: QueueFake captures dispatched jobs for assertions."""

    async def test_fake_records_dispatched_jobs(self) -> None:
        from arvel.queue.fake import QueueFake

        fake = QueueFake()
        job = SendEmailJob(to="a@b.com")
        await fake.dispatch(job)

        assert fake.pushed_count == 1

    async def test_fake_assert_pushed(self) -> None:
        from arvel.queue.fake import QueueFake

        fake = QueueFake()
        await fake.dispatch(SendEmailJob(to="a@b.com"))

        fake.assert_pushed(SendEmailJob)

    async def test_fake_assert_pushed_with(self) -> None:
        from arvel.queue.fake import QueueFake

        fake = QueueFake()
        await fake.dispatch(SendEmailJob(to="x@y.com", subject="Test"))

        fake.assert_pushed_with(SendEmailJob, to="x@y.com")

    async def test_fake_assert_nothing_pushed(self) -> None:
        from arvel.queue.fake import QueueFake

        fake = QueueFake()
        fake.assert_nothing_pushed()

    async def test_fake_assert_pushed_count(self) -> None:
        from arvel.queue.fake import QueueFake

        fake = QueueFake()
        await fake.dispatch(SendEmailJob())
        await fake.dispatch(SendEmailJob())

        assert fake.pushed_count == 2

    async def test_fake_implements_queue_contract(self) -> None:
        from arvel.queue.contracts import QueueContract
        from arvel.queue.fake import QueueFake

        fake = QueueFake()
        assert isinstance(fake, QueueContract)
