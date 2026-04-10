"""Fake driver re-exports — one import for all test doubles."""

from __future__ import annotations

from arvel.broadcasting.fake import BroadcastFake
from arvel.cache.fakes import CacheFake
from arvel.events.fake import EventFake
from arvel.lock.fakes import LockFake
from arvel.mail.fakes import MailFake
from arvel.media.fakes import MediaFake
from arvel.notifications.fakes import NotificationFake
from arvel.queue.fake import QueueFake
from arvel.storage.fakes import StorageFake

__all__ = [
    "BroadcastFake",
    "CacheFake",
    "EventFake",
    "LockFake",
    "MailFake",
    "MediaFake",
    "NotificationFake",
    "QueueFake",
    "StorageFake",
]
