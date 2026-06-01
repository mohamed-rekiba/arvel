"""BroadcastManager driver resolution."""

from __future__ import annotations

import pytest


def test_manager_default_driver_resolves_from_config() -> None:
    """default name comes from BroadcastConfig.default."""
    from arvel.broadcasting.config import BroadcastConfig, BroadcastDriver
    from arvel.broadcasting.drivers.log import LogBroadcaster
    from arvel.broadcasting.manager import BroadcastManager

    config = BroadcastConfig(default=BroadcastDriver.LOG)
    manager = BroadcastManager(config)
    driver = manager.driver()
    assert isinstance(driver, LogBroadcaster)


def test_manager_same_name_returns_same_instance() -> None:
    """per-manager singleton — same name returns same instance."""
    from arvel.broadcasting.config import BroadcastConfig, BroadcastDriver
    from arvel.broadcasting.manager import BroadcastManager

    manager = BroadcastManager(BroadcastConfig(default=BroadcastDriver.LOG))
    a = manager.driver("log")
    b = manager.driver("log")
    assert a is b


def test_manager_unknown_driver_raises() -> None:
    """unknown driver name raises BroadcastDriverError."""
    from arvel.broadcasting.config import BroadcastConfig, BroadcastDriver
    from arvel.broadcasting.exceptions import BroadcastDriverError
    from arvel.broadcasting.manager import BroadcastManager

    manager = BroadcastManager(BroadcastConfig(default=BroadcastDriver.LOG))
    with pytest.raises(BroadcastDriverError):
        manager.driver("does-not-exist")


def test_manager_resolves_null_driver() -> None:
    from arvel.broadcasting.config import BroadcastConfig, BroadcastDriver
    from arvel.broadcasting.drivers.null import NullBroadcaster
    from arvel.broadcasting.manager import BroadcastManager

    manager = BroadcastManager(BroadcastConfig(default=BroadcastDriver.NULL))
    assert isinstance(manager.driver(), NullBroadcaster)
