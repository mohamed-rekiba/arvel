"""Tests for QueueSettings — config validation, defaults, env overrides."""

from __future__ import annotations

from typing import Any, Literal, cast

import pytest

from arvel.queue.config import QueueSettings


class TestQueueSettingsDefaults:
    """Verify QueueSettings defaults when no env vars are set."""

    def test_default_driver_is_sync(self, clean_env: None) -> None:
        settings = QueueSettings()
        assert settings.driver == "sync"

    def test_default_queue_name(self, clean_env: None) -> None:
        settings = QueueSettings()
        assert settings.default == "default"

    def test_default_redis_url(self, clean_env: None) -> None:
        settings = QueueSettings()
        assert settings.redis_url == "redis://localhost:6379"

    def test_default_taskiq_broker(self, clean_env: None) -> None:
        settings = QueueSettings()
        assert settings.taskiq_broker == "redis"

    def test_default_taskiq_url_is_none(self, clean_env: None) -> None:
        settings = QueueSettings()
        assert settings.taskiq_url is None


class TestQueueSettingsEnvOverride:
    """Verify QueueSettings reads from QUEUE_* env vars."""

    def test_override_driver_taskiq(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QUEUE_DRIVER", "taskiq")
        settings = QueueSettings()
        assert settings.driver == "taskiq"

    def test_override_redis_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QUEUE_REDIS_URL", "redis://custom:6380")
        settings = QueueSettings()
        assert settings.redis_url == "redis://custom:6380"

    def test_override_default_queue_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QUEUE_DEFAULT", "emails")
        settings = QueueSettings()
        assert settings.default == "emails"

    def test_override_taskiq_broker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QUEUE_TASKIQ_BROKER", "nats")
        settings = QueueSettings()
        assert settings.taskiq_broker == "nats"

    def test_override_taskiq_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QUEUE_TASKIQ_URL", "nats://localhost:4222")
        settings = QueueSettings()
        assert settings.taskiq_url == "nats://localhost:4222"


class TestQueueSettingsValidation:
    """Verify QueueSettings validates driver and broker literals."""

    def test_invalid_driver_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QueueSettings(driver=cast("Any", "nonexistent"))

    def test_invalid_taskiq_broker_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QueueSettings(taskiq_broker=cast("Any", "kafka"))

    def test_valid_drivers_accepted(self) -> None:
        drivers: tuple[Literal["sync", "null", "taskiq"], ...] = (
            "sync",
            "null",
            "taskiq",
        )
        for driver in drivers:
            settings = QueueSettings(driver=driver)
            assert settings.driver == driver

    def test_valid_taskiq_brokers_accepted(self) -> None:
        brokers: tuple[Literal["redis", "nats", "rabbitmq", "memory"], ...] = (
            "redis",
            "nats",
            "rabbitmq",
            "memory",
        )
        for broker in brokers:
            settings = QueueSettings(taskiq_broker=broker)
            assert settings.taskiq_broker == broker
