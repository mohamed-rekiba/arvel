"""Tests for QueueConfig — NFR-008-001..006."""

from __future__ import annotations

import pytest
from arvel.queue.config import QueueConfig, QueueDriver
from pydantic import ValidationError


class TestQueueConfig:
    """NFR-008-001: Configuration via env vars with QUEUE_ prefix."""

    def test_defaults(self) -> None:
        config = QueueConfig()
        assert config.connection == QueueDriver.SYNC

    def test_custom_connection(self) -> None:
        config = QueueConfig(connection=QueueDriver.REDIS)
        assert config.connection == QueueDriver.REDIS

    def test_database_config_nested(self) -> None:
        config = QueueConfig(connection=QueueDriver.DATABASE)
        assert config.database is not None

    def test_redis_config_nested(self) -> None:
        config = QueueConfig(connection=QueueDriver.REDIS)
        assert config.redis is not None

    def test_taskiq_config_nested(self) -> None:
        config = QueueConfig(connection=QueueDriver.TASKIQ)
        assert config.taskiq is not None

    def test_invalid_connection_raises(self) -> None:
        with pytest.raises(ValidationError):
            QueueConfig.model_validate({"connection": "nonexistent"})
