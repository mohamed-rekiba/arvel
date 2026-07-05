"""arvel.queue.scheduler — the task scheduler (Laravel ``Schedule`` parity).

Define recurring work with a fluent cadence (``daily_at``/``hourly``/``cron``/frequency helpers/…);
a periodic runner (``arvel schedule:run``, doc 13) ticks once a minute and calls ``run_due(now)``.
Cron matching is a small standard 5-field implementation (no extra dependency). ``on_one_server``
and ``without_overlapping`` are coordinated via a real :class:`~arvel.cache.CacheLock` — only one
instance actually runs a one-server event's tick, and a still-running event's next tick is skipped
rather than overlapping it. Grounded in knowledge/port/12-queues.md.
"""

from __future__ import annotations

import inspect
from datetime import datetime
from typing import Any, cast

#: `on_one_server`'s lock TTL — a safety net only (the lock is always explicitly released once the
#: event finishes); this just bounds how long a crashed holder can starve other instances.
_ONE_SERVER_LOCK_TTL = 3600


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
    """One scheduled task: a callback + a cron expression + hooks/gates/frequency helpers.

    ``cache`` (usually threaded down from the owning :class:`Schedule`) backs ``on_one_server``/
    ``without_overlapping``; falls back to the app-bound default cache (``arvel.support.cache()``)
    when not given explicitly, so two separately-constructed schedulers sharing one cache backend
    (e.g. two ``schedule:run`` processes against the same Valkey) coordinate correctly.
    """

    def __init__(self, callback: Any, *, cache: Any = None) -> None:
        self.callback = callback
        self.expression = "* * * * *"
        self.one_server = False
        self.overlap_expire: int | None = None
        self._cache = cache
        self._event_name: str | None = None
        self._tz: str | None = None
        self._before: list[Any] = []
        self._after: list[Any] = []
        self._on_success: list[Any] = []
        self._on_failure: list[Any] = []
        self._when: Any = None
        self._skip: Any = None
        self._environments: tuple[str, ...] | None = None
        self._between: tuple[str, str] | None = None

    # --- cadence -------------------------------------------------------------
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

    def twice_daily(self, first: int = 1, second: int = 13) -> ScheduledEvent:
        return self.cron(f"0 {first},{second} * * *")

    def weekly(self) -> ScheduledEvent:
        return self.cron("0 0 * * 0")

    def monthly(self) -> ScheduledEvent:
        return self.cron("0 0 1 * *")

    def quarterly(self) -> ScheduledEvent:
        return self.cron("0 0 1 1,4,7,10 *")

    def yearly(self) -> ScheduledEvent:
        return self.cron("0 0 1 1 *")

    def _with_dow(self, dow: str) -> ScheduledEvent:
        minute, hour, dom, month, _ = self.expression.split()
        return self.cron(f"{minute} {hour} {dom} {month} {dow}")

    def weekdays(self) -> ScheduledEvent:
        return self._with_dow("1-5")

    def weekends(self) -> ScheduledEvent:
        return self._with_dow("0,6")

    # --- gates -----------------------------------------------------------------
    def between(self, start: str, end: str) -> ScheduledEvent:
        """Only due while the current time-of-day (``"HH:MM"``) falls within ``[start, end]``
        (wraps past midnight if ``start > end``) — a runtime gate, not a cron field."""
        self._between = (start, end)
        return self

    def when(self, callback: Any) -> ScheduledEvent:
        """Only due while ``callback()`` is truthy."""
        self._when = callback
        return self

    def skip(self, callback: Any) -> ScheduledEvent:
        """Never due while ``callback()`` is truthy (the inverse of :meth:`when`)."""
        self._skip = callback
        return self

    def environments(self, *envs: str) -> ScheduledEvent:
        """Only due when ``config('app.env')`` is one of ``envs``."""
        self._environments = envs
        return self

    def timezone(self, tz: str) -> ScheduledEvent:
        """Match the cron expression against ``moment`` shifted into ``tz`` instead of as given
        (``moment`` is otherwise assumed already in the zone you want to schedule against)."""
        self._tz = tz
        return self

    def name(self, name: str) -> ScheduledEvent:
        """An explicit identity for the ``on_one_server``/``without_overlapping`` lock key —
        needed when the callback itself has no stable qualified name (e.g. a lambda/closure)."""
        self._event_name = name
        return self

    # --- concurrency -------------------------------------------------------
    def on_one_server(self) -> ScheduledEvent:
        """Only one running scheduler instance executes this event's tick (a shared cache lock
        arbitrates — the others skip it, rather than every server double-running it)."""
        self.one_server = True
        return self

    def without_overlapping(self, expires: int = 3600) -> ScheduledEvent:
        """Skip this tick while a prior run of the same event is still in flight — ``expires``
        (seconds) is the lock's safety-net TTL if a run dies without releasing it."""
        self.overlap_expire = expires
        return self

    # --- hooks -----------------------------------------------------------------
    def before(self, callback: Any) -> ScheduledEvent:
        self._before.append(callback)
        return self

    def after(self, callback: Any) -> ScheduledEvent:
        self._after.append(callback)
        return self

    def on_success(self, callback: Any) -> ScheduledEvent:
        self._on_success.append(callback)
        return self

    def on_failure(self, callback: Any) -> ScheduledEvent:
        self._on_failure.append(callback)
        return self

    # --- due/run -----------------------------------------------------------
    def _localized(self, moment: datetime) -> datetime:
        if self._tz is None:
            return moment
        from arvel.dates import Date

        zoned = Date.from_py(moment, tz="UTC").raw.to_tz(self._tz)
        return cast("datetime", Date(zoned).to_py())

    @staticmethod
    def _within_time_range(moment: datetime, start: str, end: str) -> bool:
        current = moment.strftime("%H:%M")
        if start <= end:
            return start <= current <= end
        return current >= start or current <= end  # a range that wraps past midnight

    def _environment_matches(self) -> bool:
        from arvel.kernel.config import config_default

        return str(config_default("app.env", "local")) in (self._environments or ())

    def is_due(self, moment: datetime) -> bool:
        local_moment = self._localized(moment)
        if not cron_matches(self.expression, local_moment):
            return False
        if self._between is not None and not self._within_time_range(local_moment, *self._between):
            return False
        if self._environments is not None and not self._environment_matches():
            return False
        if self._skip is not None and self._skip():
            return False
        return not (self._when is not None and not self._when())

    def _identity(self) -> str:
        if self._event_name is not None:
            return self._event_name
        module = getattr(self.callback, "__module__", "")
        qualname = getattr(self.callback, "__qualname__", repr(self.callback))
        return f"{module}.{qualname}"

    def _lock(self, name: str, seconds: int) -> Any:
        if self._cache is not None:
            return self._cache.lock(name, seconds=seconds)
        from arvel.support import cache

        return cache().lock(name, seconds=seconds)

    @staticmethod
    async def _fire(hooks: list[Any]) -> None:
        for hook in hooks:
            outcome = hook()
            if inspect.isawaitable(outcome):
                await outcome

    async def run(self) -> Any:
        locks: list[Any] = []
        ran = False  # set only once past the locks — so before/after/callback all skip a lost tick
        try:
            if self.one_server:
                lock = self._lock(f"schedule:one_server:{self._identity()}", _ONE_SERVER_LOCK_TTL)
                if not await lock.acquire():
                    return None  # another instance already owns this tick
                locks.append(lock)
            if self.overlap_expire is not None:
                lock = self._lock(f"schedule:overlap:{self._identity()}", self.overlap_expire)
                if not await lock.acquire():
                    return None  # a prior run of this event is still in flight
                locks.append(lock)

            ran = True
            await self._fire(self._before)
            try:
                result = self.callback()
                if inspect.isawaitable(result):
                    result = await result
            except Exception:
                await self._fire(self._on_failure)
                raise
            await self._fire(self._on_success)
            return result
        finally:
            if ran:  # after-hooks fire only when the event actually ran, not on a skipped tick
                await self._fire(self._after)
            for lock in locks:  # release is unconditional — a lost tick acquired no lock anyway
                await lock.release()


class Schedule:
    """Registry of scheduled events. ``run_due(now)`` executes the ones due at ``now``."""

    def __init__(self, cache: Any = None) -> None:
        self.events: list[ScheduledEvent] = []
        self._cache = cache

    def call(self, callback: Any) -> ScheduledEvent:
        """Schedule an arbitrary callable (sync or async)."""
        event = ScheduledEvent(callback, cache=self._cache)
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
        """Run every due event. A failing event is LOGGED and skipped — one bad task must never
        starve the rest of the schedule (or kill the cron tick)."""
        for event in self.due_events(moment):
            try:
                await event.run()
            except Exception:
                from arvel.kernel.logging import LogManager

                LogManager().channel("schedule").error(
                    "scheduled_task_failed",
                    task=getattr(event.callback, "__name__", repr(event.callback)),
                    exc_info=True,
                )
