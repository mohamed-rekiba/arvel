"""ScheduledTask Pydantic model — immutable record of a registered task."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from arvel.scheduling.expressions import is_due

# Callback may be a coroutine function, a console command name, or a job class FQN.
TaskCallback = Callable[[], Awaitable[None]] | str | type[Any]


class ScheduledTask(BaseModel):
    """Immutable scheduled task — built by ScheduledTaskBuilder, stored in Schedule.tasks()."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")

    name: str = Field(min_length=1)
    description: str | None = None
    callback: TaskCallback | None = None
    callback_kind: Literal["call", "command", "job"] = "call"
    expression: str
    timezone: str = "UTC"
    without_overlapping: bool = False
    without_overlapping_ttl_minutes: int = 1440
    on_one_server: bool = False
    on_one_server_ttl_seconds: int = 60
    in_maintenance_mode: bool = False
    output_to: Path | None = None

    def is_due(self, now: datetime) -> bool:
        """True if this task is due at ``now`` in the task's configured timezone."""
        return is_due(self.expression, now=now, timezone=self.timezone)


__all__ = ["ScheduledTask", "TaskCallback"]
