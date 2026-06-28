"""arvel.queue.scheduler — the task scheduler (Laravel ``Schedule`` parity).

Define recurring work with a fluent cadence (``daily_at``/``hourly``/``cron``/…); a periodic
runner (``arvel schedule:run``, doc 13) ticks once a minute and calls ``run_due(now)``. Cron
matching is a small standard 5-field implementation (no extra dependency). ``on_one_server``
marks events that must run on a single node (coordinated via the cache lock). Grounded in
knowledge/port/12-queues.md.
"""

from __future__ import annotations

import inspect
from datetime import datetime
from typing import Any


def _field_matches(field: str, value: int) -> bool:
    if field == "*":
        return True
    for part in field.split(","):
        if part.startswith("*/"):
            if value % int(part[2:]) == 0:
                return True
        elif "-" in part:
            low, high = (int(n) for n in part.split("-"))
            if low <= value <= high:
                return True
        elif part.isdigit() and int(part) == value:
            return True
    return False


def cron_matches(expression: str, moment: datetime) -> bool:
    """Does a standard 5-field cron expression (min hour dom month dow) fire at ``moment``?"""
    minute, hour, dom, month, dow = expression.split()
    cron_dow = (moment.weekday() + 1) % 7  # python Mon=0 -> cron Sun=0
    return (
        _field_matches(minute, moment.minute)
        and _field_matches(hour, moment.hour)
        and _field_matches(dom, moment.day)
        and _field_matches(month, moment.month)
        and _field_matches(dow, cron_dow)
    )


class ScheduledEvent:
    """One scheduled task: a callback + a cron expression + an ``on_one_server`` flag."""

    def __init__(self, callback: Any) -> None:
        self.callback = callback
        self.expression = "* * * * *"
        self.one_server = False

    def cron(self, expression: str) -> ScheduledEvent:
        self.expression = expression
        return self

    def every_minute(self) -> ScheduledEvent:
        return self.cron("* * * * *")

    def hourly(self) -> ScheduledEvent:
        return self.cron("0 * * * *")

    def daily(self) -> ScheduledEvent:
        return self.cron("0 0 * * *")

    def daily_at(self, time: str) -> ScheduledEvent:
        hour, minute = (int(n) for n in time.split(":"))
        return self.cron(f"{minute} {hour} * * *")

    def on_one_server(self) -> ScheduledEvent:
        self.one_server = True
        return self

    def is_due(self, moment: datetime) -> bool:
        return cron_matches(self.expression, moment)

    async def run(self) -> Any:
        result = self.callback()
        if inspect.isawaitable(result):
            return await result
        return result


class Schedule:
    """Registry of scheduled events. ``run_due(now)`` executes the ones due at ``now``."""

    def __init__(self) -> None:
        self.events: list[ScheduledEvent] = []

    def call(self, callback: Any) -> ScheduledEvent:
        """Schedule an arbitrary callable (sync or async)."""
        event = ScheduledEvent(callback)
        self.events.append(event)
        return event

    def job(self, job: Any) -> ScheduledEvent:
        """Schedule a queued job (dispatched onto the queue when due)."""

        async def _dispatch() -> Any:
            from arvel.queue import Bus

            await Bus.chain([job]).dispatch()

        return self.call(_dispatch)

    def command(self, name: str, *args: str) -> ScheduledEvent:
        """Schedule a console command by name (run via the CLI when due)."""

        def _invoke() -> None:
            from arvel.console import build_cli

            build_cli()([name, *args], standalone_mode=False)

        return self.call(_invoke)

    def due_events(self, moment: datetime) -> list[ScheduledEvent]:
        return [event for event in self.events if event.is_due(moment)]

    async def run_due(self, moment: datetime) -> None:
        for event in self.due_events(moment):
            await event.run()
