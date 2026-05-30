"""Schedule + ScheduledTaskBuilder — fluent DSL for registering scheduled tasks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self

from arvel.scheduling.exceptions import ScheduleError
from arvel.scheduling.expressions import is_valid_expression
from arvel.scheduling.scheduled_task import ScheduledTask


def _derive_name(callback: Any) -> str:
    """Best-effort name derivation: callable.__qualname__, str, or class name."""
    if callable(callback) and not isinstance(callback, type):
        qn = getattr(callback, "__qualname__", None) or getattr(callback, "__name__", None)
        return qn or repr(callback)
    if isinstance(callback, type):
        return callback.__name__
    return str(callback)


@dataclass
class _PendingTask:
    name: str
    description: str | None = None
    callback: Any = None
    callback_kind: Literal["call", "command", "job"] = "call"
    expression: str = "* * * * *"
    timezone: str = "UTC"
    without_overlapping: bool = False
    without_overlapping_ttl_minutes: int = 1440
    on_one_server: bool = False
    on_one_server_ttl_seconds: int = 60
    in_maintenance_mode: bool = False
    output_to: Path | None = None


class ScheduledTaskBuilder:
    """Returned from Schedule.call() / .command() / .job(). All methods return self."""

    def __init__(self, schedule: Schedule, pending: _PendingTask) -> None:
        self._schedule = schedule
        self._pending = pending

    # ── Frequency modifiers ──────────────────────────────────────────────
    def cron(self, expression: str) -> Self:
        if not is_valid_expression(expression):
            raise ScheduleError(f"Invalid cron expression: {expression!r}")
        self._pending.expression = expression
        return self

    def everyMinute(self) -> Self:
        return self.cron("* * * * *")

    def everyFiveMinutes(self) -> Self:
        return self.cron("*/5 * * * *")

    def everyTenMinutes(self) -> Self:
        return self.cron("*/10 * * * *")

    def everyFifteenMinutes(self) -> Self:
        return self.cron("*/15 * * * *")

    def everyThirtyMinutes(self) -> Self:
        return self.cron("*/30 * * * *")

    def hourly(self) -> Self:
        return self.cron("0 * * * *")

    def daily(self) -> Self:
        return self.cron("0 0 * * *")

    def dailyAt(self, time: str) -> Self:
        h, m = self._parse_hhmm(time)
        return self.cron(f"{m} {h} * * *")

    def weeklyOn(self, day: int, time: str = "00:00") -> Self:
        h, m = self._parse_hhmm(time)
        if not 0 <= day <= 6:
            raise ScheduleError(f"weeklyOn day must be 0-6 (0=Sun), got {day}")
        return self.cron(f"{m} {h} * * {day}")

    def monthly(self) -> Self:
        return self.cron("0 0 1 * *")

    def monthlyOn(self, day: int, time: str = "00:00") -> Self:
        h, m = self._parse_hhmm(time)
        if not 1 <= day <= 31:
            raise ScheduleError(f"monthlyOn day must be 1-31, got {day}")
        return self.cron(f"{m} {h} {day} * *")

    def yearly(self) -> Self:
        return self.cron("0 0 1 1 *")

    @staticmethod
    def _parse_hhmm(time: str) -> tuple[int, int]:
        try:
            hh, mm = time.split(":", 1)
            h, m = int(hh), int(mm)
        except (ValueError, AttributeError) as e:
            raise ScheduleError(f"time must be 'HH:MM', got {time!r}") from e
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ScheduleError(f"time out of range: {time!r}")
        return h, m

    # ── Modifiers ────────────────────────────────────────────────────────
    def name(self, value: str) -> Self:
        if not value:
            raise ScheduleError("name must be non-empty")
        self._pending.name = value
        return self

    def description(self, text: str) -> Self:
        self._pending.description = text
        return self

    def timezone(self, tz: str) -> Self:
        self._pending.timezone = tz
        return self

    def withoutOverlapping(self, ttl_minutes: int = 1440) -> Self:
        self._pending.without_overlapping = True
        self._pending.without_overlapping_ttl_minutes = ttl_minutes
        return self

    def onOneServer(self, ttl_seconds: int = 60) -> Self:
        self._pending.on_one_server = True
        self._pending.on_one_server_ttl_seconds = ttl_seconds
        return self

    def inMaintenanceMode(self) -> Self:
        self._pending.in_maintenance_mode = True
        return self

    def outputTo(self, path: Path) -> Self:
        self._pending.output_to = path
        return self


class Schedule:
    """Fluent task registration builder. One instance per Application."""

    def __init__(self) -> None:
        self._pending: list[_PendingTask] = []

    def call(self, callback: Callable[[], Awaitable[None]]) -> ScheduledTaskBuilder:
        pending = _PendingTask(name=_derive_name(callback), callback=callback, callback_kind="call")
        self._pending.append(pending)
        return ScheduledTaskBuilder(self, pending)

    def command(self, name: str) -> ScheduledTaskBuilder:
        pending = _PendingTask(name=f"command:{name}", callback=name, callback_kind="command")
        self._pending.append(pending)
        return ScheduledTaskBuilder(self, pending)

    def job(self, job_class: type[Any]) -> ScheduledTaskBuilder:
        pending = _PendingTask(
            name=f"job:{_derive_name(job_class)}", callback=job_class, callback_kind="job"
        )
        self._pending.append(pending)
        return ScheduledTaskBuilder(self, pending)

    def tasks(self) -> tuple[ScheduledTask, ...]:
        """Snapshot of currently-registered tasks as frozen ScheduledTask models."""
        return tuple(
            ScheduledTask(
                name=p.name,
                description=p.description,
                callback=p.callback,
                callback_kind=p.callback_kind,
                expression=p.expression,
                timezone=p.timezone,
                without_overlapping=p.without_overlapping,
                without_overlapping_ttl_minutes=p.without_overlapping_ttl_minutes,
                on_one_server=p.on_one_server,
                on_one_server_ttl_seconds=p.on_one_server_ttl_seconds,
                in_maintenance_mode=p.in_maintenance_mode,
                output_to=p.output_to,
            )
            for p in self._pending
        )


__all__ = ["Schedule", "ScheduledTaskBuilder"]
