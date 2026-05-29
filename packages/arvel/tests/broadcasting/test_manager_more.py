"""BroadcastManager edge branches."""

from __future__ import annotations

import importlib

import pytest
from arvel.broadcasting.config import BroadcastConfig, BroadcastDriver
from arvel.broadcasting.drivers.log import LogBroadcaster
from arvel.broadcasting.drivers.null import NullBroadcaster
from arvel.broadcasting.exceptions import BroadcastDriverError
from arvel.broadcasting.manager import BroadcastManager


class _Channel:
    pass


def test_broadcast_manager_channels_and_cached_drivers() -> None:
    manager = BroadcastManager(BroadcastConfig(default=BroadcastDriver.NULL))

    manager.register_channel("orders.{id}", _Channel)

    assert manager.config.default is BroadcastDriver.NULL
    assert manager.channels() == {"orders.{id}": _Channel}
    assert isinstance(manager.driver(), NullBroadcaster)
    assert manager.driver() is manager.driver()
    assert isinstance(manager.driver("log"), LogBroadcaster)


def test_broadcast_manager_rejects_unknown_and_pusher_drivers() -> None:
    manager = BroadcastManager(BroadcastConfig())

    with pytest.raises(BroadcastDriverError, match="Unknown broadcast driver"):
        manager.driver("unknown")

    with pytest.raises(BroadcastDriverError, match="cannot be auto-built"):
        manager.driver("pusher")


def test_broadcast_manager_redis_driver_reports_missing_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def import_module(name: str) -> object:
        if name == "redis.asyncio":
            raise ImportError("missing redis")
        return importlib.import_module(name)

    monkeypatch.setattr(importlib, "import_module", import_module)
    manager = BroadcastManager(BroadcastConfig(default=BroadcastDriver.REDIS_PUBSUB))

    with pytest.raises(BroadcastDriverError, match=r"arvel\[redis\]"):
        manager.driver()
