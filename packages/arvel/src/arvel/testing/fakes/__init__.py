"""Facade fakes — in-memory test doubles with assertion helpers."""

from arvel.testing.fakes.cache import CacheFakeContext
from arvel.testing.fakes.event import EventFake, EventFakeContext
from arvel.testing.fakes.lock import LockFake
from arvel.testing.fakes.storage import StorageFake, StorageFakeContext

__all__ = [
    "CacheFakeContext",
    "EventFake",
    "EventFakeContext",
    "LockFake",
    "StorageFake",
    "StorageFakeContext",
]
