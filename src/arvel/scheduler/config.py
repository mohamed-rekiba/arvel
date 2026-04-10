"""Scheduler configuration — env-driven via pydantic-settings."""

from __future__ import annotations

from typing import ClassVar, Literal

from arvel.foundation.config import ModuleSettings


class SchedulerSettings(ModuleSettings):
    """Configuration for the task scheduler.

    Env vars are prefixed with ``SCHEDULER_``:
      - ``SCHEDULER_ENABLED`` — enable/disable the scheduler
      - ``SCHEDULER_TIMEZONE`` — default timezone for cron evaluation
      - ``SCHEDULER_LOCK_BACKEND`` — lock backend for overlap prevention
    """

    model_config: ClassVar[dict[str, str]] = {"env_prefix": "SCHEDULER_"}

    enabled: bool = True
    timezone: str = "UTC"
    lock_backend: Literal["memory", "null"] = "memory"


settings_class = SchedulerSettings
