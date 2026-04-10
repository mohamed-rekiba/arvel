"""Tests for fake driver assertion enrichment — Story 3, all 10 ACs."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from arvel.cache.fakes import CacheFake
from arvel.events.event import Event
from arvel.events.fake import EventFake
from arvel.mail.fakes import MailFake
from arvel.mail.mailable import Mailable
from arvel.media.fakes import MediaFake
from arvel.notifications.fakes import NotificationFake
from arvel.notifications.notification import Notification
from arvel.queue.fake import QueueFake
from arvel.queue.job import Job
from arvel.storage.fakes import StorageFake


@dataclass
class SampleMailable(Mailable):
    to: list[str] = field(default_factory=list)
    subject: str = "Test"


class SampleEvent(Event):
    user_id: int


class OtherEvent(Event):
    order_id: int


class SampleJob(Job):
    queue_name: str = "default"

    async def handle(self) -> None:
        pass


class HighPriorityJob(SampleJob):
    queue_name: str = "high"


class SampleNotification(Notification):
    pass


class TestMailFakeAssertions:
    """AC-S3-1 to AC-S3-3: MailFake assertion methods."""

    @pytest.mark.anyio
    async def test_assert_sent_passes(self) -> None:
        mail = MailFake()
        mailable = SampleMailable(to=["alice@test.com"], subject="Welcome")
        await mail.send(mailable)
        mail.assert_sent(subject="Welcome")

    @pytest.mark.anyio
    async def test_assert_not_sent_passes(self) -> None:
        mail = MailFake()
        mail.assert_not_sent(subject="Welcome")

    @pytest.mark.anyio
    async def test_assert_not_sent_fails(self) -> None:
        mail = MailFake()
        mailable = SampleMailable(to=["a@t.com"], subject="Welcome")
        await mail.send(mailable)
        with pytest.raises(AssertionError, match="not to be sent"):
            mail.assert_not_sent(subject="Welcome")

    @pytest.mark.anyio
    async def test_assert_sent_count(self) -> None:
        mail = MailFake()
        for _ in range(2):
            await mail.send(SampleMailable(to=["a@t.com"]))
        mail.assert_sent_count(2)

    @pytest.mark.anyio
    async def test_assert_sent_count_mismatch(self) -> None:
        mail = MailFake()
        await mail.send(SampleMailable(to=["a@t.com"]))
        with pytest.raises(AssertionError, match="Expected 5"):
            mail.assert_sent_count(5)


class TestEventFakeAssertions:
    """AC-S3-4 to AC-S3-5: EventFake with predicate."""

    @pytest.mark.anyio
    async def test_assert_dispatched_passes(self) -> None:
        events = EventFake()
        await events.dispatch(SampleEvent(user_id=42))
        events.assert_dispatched(SampleEvent)

    @pytest.mark.anyio
    async def test_assert_dispatched_with_predicate(self) -> None:
        events = EventFake()
        await events.dispatch(SampleEvent(user_id=42))
        events.assert_dispatched(SampleEvent, lambda e: e.user_id == 42)

    @pytest.mark.anyio
    async def test_assert_dispatched_predicate_no_match(self) -> None:
        events = EventFake()
        await events.dispatch(SampleEvent(user_id=42))
        with pytest.raises(AssertionError, match="matching predicate"):
            events.assert_dispatched(SampleEvent, lambda e: e.user_id == 999)

    @pytest.mark.anyio
    async def test_assert_dispatched_count(self) -> None:
        events = EventFake()
        await events.dispatch(SampleEvent(user_id=1))
        await events.dispatch(SampleEvent(user_id=2))
        await events.dispatch(OtherEvent(order_id=1))
        events.assert_dispatched_count(SampleEvent, 2)

    @pytest.mark.anyio
    async def test_assert_dispatched_count_mismatch(self) -> None:
        events = EventFake()
        await events.dispatch(SampleEvent(user_id=1))
        with pytest.raises(AssertionError, match="Expected 3"):
            events.assert_dispatched_count(SampleEvent, 3)


class TestQueueFakeAssertions:
    """AC-S3-6 to AC-S3-7: QueueFake pushed_on and count."""

    @pytest.mark.anyio
    async def test_assert_pushed_on_passes(self) -> None:
        queue = QueueFake()
        job = HighPriorityJob()
        await queue.dispatch(job)
        queue.assert_pushed_on("high", HighPriorityJob)

    @pytest.mark.anyio
    async def test_assert_pushed_on_fails(self) -> None:
        queue = QueueFake()
        job = SampleJob()
        await queue.dispatch(job)
        with pytest.raises(AssertionError, match="on queue 'high'"):
            queue.assert_pushed_on("high", SampleJob)

    @pytest.mark.anyio
    async def test_assert_pushed_count(self) -> None:
        queue = QueueFake()
        await queue.dispatch(SampleJob())
        await queue.dispatch(SampleJob())
        queue.assert_pushed_count(SampleJob, 2)


class TestNotificationFakeAssertions:
    """AC-S3-8: NotificationFake combined notifiable + type check."""

    @pytest.mark.anyio
    async def test_assert_sent_to_with_type(self) -> None:
        notif = NotificationFake()
        user = {"id": 42}
        await notif.send(user, SampleNotification())
        notif.assert_sent_to(user, SampleNotification)

    @pytest.mark.anyio
    async def test_assert_sent_to_wrong_type(self) -> None:
        notif = NotificationFake()
        user = {"id": 42}
        await notif.send(user, SampleNotification())

        class OtherNotification(Notification):
            pass

        with pytest.raises(AssertionError):
            notif.assert_sent_to(user, OtherNotification)


class TestCacheFakeAssertions:
    """AC-S3-9: CacheFake negative assertions."""

    @pytest.mark.anyio
    async def test_assert_not_put(self) -> None:
        cache = CacheFake()
        cache.assert_not_put("missing-key")

    @pytest.mark.anyio
    async def test_assert_not_put_fails(self) -> None:
        cache = CacheFake()
        await cache.put("my-key", "value")
        with pytest.raises(AssertionError, match="not to be put"):
            cache.assert_not_put("my-key")

    @pytest.mark.anyio
    async def test_assert_nothing_put(self) -> None:
        cache = CacheFake()
        cache.assert_nothing_put()

    @pytest.mark.anyio
    async def test_assert_nothing_put_fails(self) -> None:
        cache = CacheFake()
        await cache.put("key", "val")
        with pytest.raises(AssertionError, match="no cache puts"):
            cache.assert_nothing_put()


class TestStorageFakeAssertions:
    """StorageFake negative assertions."""

    @pytest.mark.anyio
    async def test_assert_not_stored(self) -> None:
        storage = StorageFake()
        storage.assert_not_stored("missing.txt")

    @pytest.mark.anyio
    async def test_assert_not_stored_fails(self) -> None:
        storage = StorageFake()
        await storage.put("file.txt", b"data")
        with pytest.raises(AssertionError, match="not to be stored"):
            storage.assert_not_stored("file.txt")

    @pytest.mark.anyio
    async def test_assert_nothing_stored(self) -> None:
        storage = StorageFake()
        storage.assert_nothing_stored()


class TestMediaFakeAssertions:
    """MediaFake assertion methods."""

    @pytest.mark.anyio
    async def test_assert_added(self) -> None:
        media = MediaFake()
        model = {"type": "User", "id": 1}
        await media.add(model, b"data", "file.jpg", collection="avatars")
        media.assert_added("avatars")

    @pytest.mark.anyio
    async def test_assert_added_fails(self) -> None:
        media = MediaFake()
        with pytest.raises(AssertionError, match="Expected media added"):
            media.assert_added("avatars")

    @pytest.mark.anyio
    async def test_assert_nothing_added(self) -> None:
        media = MediaFake()
        media.assert_nothing_added()

    @pytest.mark.anyio
    async def test_assert_nothing_added_fails(self) -> None:
        media = MediaFake()
        await media.add({"type": "User", "id": 1}, b"x", "f.jpg")
        with pytest.raises(AssertionError, match="no media"):
            media.assert_nothing_added()

    @pytest.mark.anyio
    async def test_assert_added_count(self) -> None:
        media = MediaFake()
        model = {"type": "User", "id": 1}
        await media.add(model, b"a", "a.jpg")
        await media.add(model, b"b", "b.jpg")
        media.assert_added_count(2)
