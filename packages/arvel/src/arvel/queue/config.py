"""Queue subsystem configuration (``QUEUE_*`` env vars)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from arvel.config.settings import ArvelSettings


class QueueDriver(StrEnum):
    SYNC = "sync"
    DATABASE = "database"
    REDIS = "redis"
    TASKIQ = "taskiq"


class DatabaseQueueConfig(ArvelSettings):
    model_config = SettingsConfigDict(env_prefix="QUEUE_DATABASE_", extra="ignore")

    table: str = "jobs"
    connection: str = "default"
    # Visibility timeout (seconds). A reserved job whose worker crashed becomes
    # claimable again after this long. Must exceed your longest job runtime, or a
    # slow job gets redelivered and runs twice. Matches Laravel's retry_after.
    retry_after: int = 90


class RedisQueueConfig(ArvelSettings):
    model_config = SettingsConfigDict(env_prefix="QUEUE_REDIS_", extra="ignore")

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: SecretStr = SecretStr("")
    queue_key: str = "arvel_queue"


class TaskiqQueueConfig(ArvelSettings):
    # ``dotenv_filtering="match_prefix"`` is required *here* (not on the base):
    # without it, a shared ``.env`` with unrelated keys (``APP_NAME``,
    # ``DB_URL``, ...) would trip ``extra="forbid"`` on every CLI load.
    model_config = SettingsConfigDict(
        env_prefix="QUEUE_TASKIQ_",
        extra="forbid",
        dotenv_filtering="match_prefix",
    )

    broker_url: str = "redis://localhost:6379/0"


class QueueConfig(ArvelSettings):
    """Queue subsystem settings.

    Env vars (auto-prefixed ``QUEUE_``):

    - ``QUEUE_CONNECTION``  (default: ``sync``)
    """

    __config_path__ = "queue"

    connection: QueueDriver = QueueDriver.SYNC

    database: DatabaseQueueConfig = DatabaseQueueConfig()
    redis: RedisQueueConfig = RedisQueueConfig()
    taskiq: TaskiqQueueConfig = TaskiqQueueConfig()


__all__ = [
    "DatabaseQueueConfig",
    "QueueConfig",
    "QueueDriver",
    "RedisQueueConfig",
    "TaskiqQueueConfig",
]
