"""Tests for fakes re-export — FR-014 to FR-015."""

from __future__ import annotations


class TestFakesReExport:
    def test_cache_fake_importable(self) -> None:
        """FR-014: CacheFake importable from arvel.testing.fakes."""
        from arvel.testing.fakes import CacheFake

        fake = CacheFake()
        assert hasattr(fake, "assert_put")

    def test_mail_fake_importable(self) -> None:
        """FR-014: MailFake importable from arvel.testing.fakes."""
        from arvel.testing.fakes import MailFake

        fake = MailFake()
        assert hasattr(fake, "assert_sent")

    def test_queue_fake_importable(self) -> None:
        """FR-014: QueueFake importable from arvel.testing.fakes."""
        from arvel.testing.fakes import QueueFake

        fake = QueueFake()
        assert hasattr(fake, "assert_pushed")

    def test_event_fake_importable(self) -> None:
        """FR-014: EventFake importable from arvel.testing.fakes."""
        from arvel.testing.fakes import EventFake

        fake = EventFake()
        assert hasattr(fake, "assert_dispatched")

    def test_notification_fake_importable(self) -> None:
        """FR-014: NotificationFake importable from arvel.testing.fakes."""
        from arvel.testing.fakes import NotificationFake

        fake = NotificationFake()
        assert hasattr(fake, "assert_sent_to")

    def test_storage_fake_importable(self) -> None:
        """FR-014: StorageFake importable from arvel.testing.fakes."""
        from arvel.testing.fakes import StorageFake

        fake = StorageFake()
        assert hasattr(fake, "assert_stored")

    def test_lock_fake_importable(self) -> None:
        """FR-014: LockFake importable from arvel.testing.fakes."""
        from arvel.testing.fakes import LockFake

        fake = LockFake()
        assert hasattr(fake, "assert_acquired")

    def test_media_fake_importable(self) -> None:
        """FR-014: MediaFake importable from arvel.testing.fakes."""
        from arvel.testing.fakes import MediaFake

        fake = MediaFake()
        assert fake is not None
