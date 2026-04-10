"""Testing support — TestClient, DatabaseTestCase, ModelFactory, fakes.

All contract test doubles (fakes) are re-exported here so users can write::

    from arvel.testing import CacheFake, MailFake
"""

from __future__ import annotations

from arvel.testing.assertions import TestResponse as TestResponse
from arvel.testing.client import TestClient as TestClient
from arvel.testing.database import DatabaseTestCase as DatabaseTestCase
from arvel.testing.factory import FactoryBuilder as FactoryBuilder
from arvel.testing.factory import ModelFactory as ModelFactory
from arvel.testing.fakes import (
    BroadcastFake as BroadcastFake,
)
from arvel.testing.fakes import (
    CacheFake as CacheFake,
)
from arvel.testing.fakes import (
    EventFake as EventFake,
)
from arvel.testing.fakes import (
    LockFake as LockFake,
)
from arvel.testing.fakes import (
    MailFake as MailFake,
)
from arvel.testing.fakes import (
    MediaFake as MediaFake,
)
from arvel.testing.fakes import (
    NotificationFake as NotificationFake,
)
from arvel.testing.fakes import (
    QueueFake as QueueFake,
)
from arvel.testing.fakes import (
    StorageFake as StorageFake,
)

__all__ = [
    "BroadcastFake",
    "CacheFake",
    "DatabaseTestCase",
    "EventFake",
    "FactoryBuilder",
    "LockFake",
    "MailFake",
    "MediaFake",
    "ModelFactory",
    "NotificationFake",
    "QueueFake",
    "StorageFake",
    "TestClient",
    "TestResponse",
]
