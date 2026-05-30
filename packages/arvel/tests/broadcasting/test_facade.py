"""FR-013-007 — Broadcast facade."""

from __future__ import annotations

import pytest


def test_facade_has_required_methods() -> None:
    from arvel.facades.broadcast import Broadcast

    assert hasattr(Broadcast, "send")
    assert hasattr(Broadcast, "channel")
    assert hasattr(Broadcast, "driver")


def test_facade_channel_returns_decorator() -> None:
    """FR-013-007 AC2: @Broadcast.channel("pattern") returns a decorator."""
    from arvel.facades.broadcast import Broadcast

    decorator = Broadcast.channel("private-test.{id}")
    assert callable(decorator)

    # Clean up — registry is module-level; we register and unregister.
    async def _cb(user: object, id: str) -> bool:
        return True

    decorator(_cb)
    # Cleanup — pop the just-registered pattern so this test is idempotent.
    Broadcast.registry().unregister("private-test.{id}")


@pytest.mark.asyncio
async def test_facade_driver_delegates_to_manager() -> None:
    """FR-013-007 AC3: facade.driver() delegates to BroadcastManager."""
    from arvel.broadcasting.config import BroadcastConfig, BroadcastDriver
    from arvel.broadcasting.drivers.null import NullBroadcaster
    from arvel.broadcasting.manager import BroadcastManager
    from arvel.facades.broadcast import Broadcast

    manager = BroadcastManager(BroadcastConfig(default=BroadcastDriver.NULL))
    Broadcast.set_manager(manager)
    try:
        assert isinstance(Broadcast.driver(), NullBroadcaster)
    finally:
        Broadcast.set_manager(None)


def test_facade_unbound_raises() -> None:
    """Calling driver/send before facade is bound raises a clear error."""
    from arvel.facades.broadcast import Broadcast

    Broadcast.set_manager(None)
    with pytest.raises(RuntimeError, match="not bound"):
        Broadcast.driver()
