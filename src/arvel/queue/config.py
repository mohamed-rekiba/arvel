"""Queue configuration — driver selection and connection settings."""

from __future__ import annotations

from typing import ClassVar, Literal

from arvel.foundation.config import ModuleSettings


class QueueSettings(ModuleSettings):
    """Configuration for the queue subsystem.

    Env vars are prefixed with ``QUEUE_``:
      - ``QUEUE_DRIVER`` — which driver to use
      - ``QUEUE_DEFAULT`` — default queue name
      - ``QUEUE_REDIS_URL`` — Redis connection (Taskiq-Redis)
      - ``QUEUE_TASKIQ_BROKER`` — Taskiq broker backend
      - ``QUEUE_TASKIQ_URL`` — Taskiq broker URL (falls back to redis_url for redis)
    """

    model_config: ClassVar[dict[str, str | bool]] = {
        "env_prefix": "QUEUE_",
    }

    driver: Literal["sync", "null", "taskiq"] = "sync"
    default: str = "default"
    redis_url: str = "redis://localhost:6379"
    taskiq_broker: Literal["redis", "nats", "rabbitmq", "memory"] = "redis"
    taskiq_url: str | None = None


settings_class = QueueSettings
