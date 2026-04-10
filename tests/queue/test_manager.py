"""Tests for QueueManager — driver resolution, unknown driver, custom drivers."""

from __future__ import annotations

from importlib import util
from typing import Literal

import pytest

from arvel.foundation.exceptions import ConfigurationError
from arvel.queue.config import QueueSettings
from arvel.queue.contracts import QueueContract
from arvel.queue.drivers.null_driver import NullQueue
from arvel.queue.drivers.sync_driver import SyncQueue
from arvel.queue.manager import QueueManager

_has_taskiq = util.find_spec("taskiq") is not None
_requires_taskiq = pytest.mark.skipif(not _has_taskiq, reason="taskiq not installed")


class TestQueueManagerBuiltinDrivers:
    """QueueManager resolves built-in drivers from settings."""

    def test_resolve_sync_driver(self) -> None:
        manager = QueueManager()
        driver_name: Literal["sync"] = "sync"
        settings = QueueSettings(driver=driver_name)
        driver = manager.create_driver(settings)
        assert isinstance(driver, SyncQueue)

    def test_resolve_null_driver(self) -> None:
        manager = QueueManager()
        driver_name: Literal["null"] = "null"
        settings = QueueSettings(driver=driver_name)
        driver = manager.create_driver(settings)
        assert isinstance(driver, NullQueue)

    @_requires_taskiq
    def test_resolve_taskiq_driver(self) -> None:
        manager = QueueManager()
        settings = QueueSettings(driver="taskiq", taskiq_broker="memory")
        driver = manager.create_driver(settings)
        assert isinstance(driver, QueueContract)
        assert type(driver).__name__ == "TaskiqQueue"

    def test_default_settings_returns_sync(self) -> None:
        manager = QueueManager()
        driver = manager.create_driver()
        assert isinstance(driver, SyncQueue)


class TestQueueManagerUnknownDriver:
    """QueueManager raises ConfigurationError for unknown driver names."""

    def test_unknown_driver_raises_configuration_error(self) -> None:
        manager = QueueManager()
        settings = QueueSettings.model_construct(driver="nonexistent")

        with pytest.raises(ConfigurationError, match="Unknown queue driver"):
            manager.create_driver(settings)

    def test_error_message_lists_available_drivers(self) -> None:
        manager = QueueManager()
        settings = QueueSettings.model_construct(driver="bad")

        with pytest.raises(ConfigurationError, match=r"null.*sync.*taskiq"):
            manager.create_driver(settings)


class TestQueueManagerCustomDrivers:
    """QueueManager supports registering custom drivers."""

    def test_register_and_resolve_custom_driver(self) -> None:
        manager = QueueManager()
        custom_queue = NullQueue()
        manager.register_driver("custom", lambda: custom_queue)

        settings = QueueSettings.model_construct(driver="custom")
        driver = manager.create_driver(settings)
        assert driver is custom_queue

    def test_custom_driver_overrides_builtin(self) -> None:
        manager = QueueManager()
        override = NullQueue()
        manager.register_driver("sync", lambda: override)

        driver_name: Literal["sync"] = "sync"
        settings = QueueSettings(driver=driver_name)
        driver = manager.create_driver(settings)
        assert driver is override

    def test_custom_driver_appears_in_error_available_list(self) -> None:
        manager = QueueManager()
        manager.register_driver("kafka", lambda: NullQueue())

        settings = QueueSettings.model_construct(driver="bad")
        with pytest.raises(ConfigurationError, match="kafka"):
            manager.create_driver(settings)
