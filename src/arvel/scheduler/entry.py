"""ScheduleEntry — fluent builder for defining recurring job schedules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self
from zoneinfo import ZoneInfo

from croniter import croniter

from arvel.foundation.exceptions import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from arvel.queue.job import Job


class ScheduleEntry:
    """A single scheduled job with its cron expression, conditions, and options."""

    def __init__(self, job_class: type[Job]) -> None:
        self.job_class = job_class
        self.expression: str = "* * * * *"
        self.tz_name: str = "UTC"
        self.prevent_overlap: bool = False
        self.overlap_expires_after: int = 1800
        self._when_callbacks: list[Callable[[], bool]] = []
        self._skip_callbacks: list[Callable[[], bool]] = []

    def cron(self, expression: str) -> Self:
        """Set an arbitrary 5-field cron expression. Validates immediately."""
        if not croniter.is_valid(expression):
            raise ConfigurationError(
                f"Invalid cron expression: {expression!r}",
                field="cron",
            )
        self.expression = expression
        return self

    def every_minute(self) -> Self:
        self.expression = "* * * * *"
        return self

    def every_five_minutes(self) -> Self:
        self.expression = "*/5 * * * *"
        return self

    def every_fifteen_minutes(self) -> Self:
        self.expression = "*/15 * * * *"
        return self

    def every_thirty_minutes(self) -> Self:
        self.expression = "*/30 * * * *"
        return self

    def hourly(self) -> Self:
        self.expression = "0 * * * *"
        return self

    def daily(self) -> Self:
        self.expression = "0 0 * * *"
        return self

    def daily_at(self, time: str) -> Self:
        """Schedule at a specific time daily. Format: ``HH:MM``."""
        parts = time.split(":")
        if len(parts) != 2:
            raise ConfigurationError(
                f"Invalid time format: {time!r}. Expected HH:MM",
                field="daily_at",
            )
        hour, minute = int(parts[0]), int(parts[1])
        self.expression = f"{minute} {hour} * * *"
        return self

    def weekly(self) -> Self:
        self.expression = "0 0 * * 0"
        return self

    def monthly(self) -> Self:
        self.expression = "0 0 1 * *"
        return self

    def timezone(self, tz: str) -> Self:
        self.tz_name = tz
        return self

    def when(self, callback: Callable[[], bool]) -> Self:
        self._when_callbacks.append(callback)
        return self

    def skip(self, callback: Callable[[], bool]) -> Self:
        self._skip_callbacks.append(callback)
        return self

    def without_overlapping(self, expires_after: int = 1800) -> Self:
        self.prevent_overlap = True
        self.overlap_expires_after = expires_after
        return self

    def should_run(self) -> bool:
        """Evaluate when/skip conditions. Returns True if the entry should dispatch."""
        for cb in self._when_callbacks:
            if not cb():
                return False
        return all(not cb() for cb in self._skip_callbacks)

    def is_due(self, now: datetime) -> bool:
        """Check if this entry is due at the given time, respecting timezone."""
        tz = ZoneInfo(self.tz_name)
        now_in_tz = now.astimezone(tz)
        return croniter.match(self.expression, now_in_tz)
