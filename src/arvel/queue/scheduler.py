"""arvel.queue.scheduler — the task scheduler.

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

#: `on_one_server`'s claim TTL. The claim is minute-scoped and held (not released) so any later
#: same-minute tick on another instance skips; the TTL just bounds how long a stale claim lingers
#: (a different minute always uses a different key, so this never cross-blocks the next tick).
_ONE_SERVER_LOCK_TTL = 3600


_CRON_MONTHS = {
    m: i
    for i, m in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1
    )
}
_CRON_DOWS = {d: i for i, d in enumerate(("sun", "mon", "tue", "wed", "thu", "fri", "sat"), 0)}


def _cron_int(token: str, names: dict[str, int] | None = None) -> int:
    t = token.strip().lower()
    if names is not None and t in names:  # names are field-scoped: months only in the month field
        return names[t]
    return int(t)


def _field_matches(field: str, value: int, names: dict[str, int] | None = None) -> bool:
    if field == "*":
        return True
    for part in field.split(","):
        rng, _, step_str = part.partition("/")  # optional step: "range/step" or "*/step"
        step = int(step_str) if step_str else 1
        if step <= 0:
            continue  # a zero/negative step matches nothing rather than dividing by zero
        if rng == "*":
            if value % step == 0:
                return True
        elif "-" in rng:  # a range, possibly stepped: "1-30/10", "mon-fri"
            low_str, _, high_str = rng.partition("-")
            low, high = _cron_int(low_str, names), _cron_int(high_str, names)
            if low <= value <= high and (value - low) % step == 0:
                return True
        else:  # a single value or name, with an optional open-ended step ("5/2" → 5,7,9,…)
            start = _cron_int(rng, names)
            if step_str:
                if value >= start and (value - start) % step == 0:
                    return True
            elif start == value:
                return True
    return False


def cron_matches(expression: str, moment: datetime) -> bool:
    """Does a standard 5-field cron expression (min hour dom month dow) fire at ``moment``?

    A malformed field (bad number, or an alias in the wrong field like a weekday name where a
    month belongs) makes the expression not match rather than raising — so one bad schedule can
    never fire at the wrong time nor abort the whole tick."""
    try:
        minute, hour, dom, month, dow = expression.split()
        cron_dow = (moment.weekday() + 1) % 7  # python Mon=0 -> cron Sun=0
        # cron also accepts 7 for Sunday, so match Sunday against either 0 or 7
        dow_ok = _field_matches(dow, cron_dow, _CRON_DOWS) or (
            cron_dow == 0 and _field_matches(dow, 7, _CRON_DOWS)
        )
        return (
            _field_matches(minute, moment.minute)
            and _field_matches(hour, moment.hour)
            and _field_matches(dom, moment.day)
            and _field_matches(month, moment.month, _CRON_MONTHS)
            and dow_ok
        )
    except ValueError:
        return False


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
        self._even_in_maintenance_mode = False

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

    def even_in_maintenance_mode(self) -> ScheduledEvent:
        """Opt this task out of the maintenance-mode skip (below) — it still runs while the app
        is down (``arvel down``), unlike every other scheduled task."""
        self._even_in_maintenance_mode = True
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
    async def _in_maintenance_mode() -> bool:
        """Whether the app is currently down for maintenance (``arvel down``) — queue is a
        higher layer than http in the module DAG (G1), so this lazy import is a permitted
        forward reference, not a back-edge; the check is skipped (never blocks) with no app
        bound (no maintenance state exists to check)."""
        from arvel.kernel import has_application

        if not has_application():
            return False
        from arvel.http.maintenance import is_down

        return await is_down()

    @staticmethod
    async def _fire(hooks: list[Any]) -> None:
        for hook in hooks:
            outcome = hook()
            if inspect.isawaitable(outcome):
                await outcome

    async def run(self, moment: datetime | None = None) -> Any:
        release_locks: list[Any] = []  # freed in finally; the one-server claim is NOT (see below)
        ran = False  # set only once past the locks — so before/after/callback all skip a lost tick
        try:
            if not self._even_in_maintenance_mode and await self._in_maintenance_mode():
                return None  # the app is down for maintenance and this task didn't opt in
            if self.one_server:
                # scope the claim to this minute and DON'T release it: a staggered tick that starts
                # after this one finishes must still find the minute claimed and skip. Releasing on
                # completion (the old behavior) let a later same-minute tick re-acquire and re-run.
                bucket = self._localized(moment or datetime.now()).strftime("%Y%m%d%H%M")
                lock = self._lock(
                    f"schedule:one_server:{self._identity()}:{bucket}", _ONE_SERVER_LOCK_TTL
                )
                if not await lock.acquire():
                    return None  # another instance already ran (or is running) this minute's tick
            if self.overlap_expire is not None:
                lock = self._lock(f"schedule:overlap:{self._identity()}", self.overlap_expire)
                if not await lock.acquire():
                    return None  # a prior run of this event is still in flight
                release_locks.append(lock)

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
            # overlap lock only; the one-server claim is left to expire with its TTL
            for lock in release_locks:
                await lock.release()


async def _dispatch_scheduled_command(name: str, args: tuple[str, ...]) -> None:
    """Dispatch a scheduled console command when due, without blocking the scheduler's own event
    loop for its full duration (6.2a).

    A **zero-arg** app-registered command — a ``routes/console.py`` closure or a provider
    ``Command`` class, the common case for a scheduled task — runs directly on this loop via
    :func:`arvel.console.kernel.run_app_command_async`: no thread, no CLI/click re-parsing (an
    app is always active here — a scheduler tick only ever runs inside one). Anything else (a
    built-in framework command, or one that takes args) still goes through the ordinary CLI
    dispatch (``build_cli()``), moved onto a worker thread (``run_in_executor``) so a slow one
    can't stall a same-tick sibling either.

    ponytail: argv→kwargs re-parsing for an *args-taking* app command isn't reimplemented here
    (that's click/Typer's own signature machinery — see ``console.lazy``); add the loop-native
    path for it too if scheduling a slow command *with* arguments turns out to need it.
    """
    if not args:
        from arvel.console.kernel import (
            command_name,
            run_app_command_async,
            run_command_class_async,
        )
        from arvel.kernel import app as active_app
        from arvel.kernel import has_application

        if has_application():
            application = active_app()
            closure = application.registry("console.closure_commands", dict).get(name)
            if closure is not None:

                async def _run_closure(app: Any) -> None:
                    result = app.call(closure.handler)
                    if inspect.isawaitable(result):
                        await result

                await run_app_command_async(_run_closure)
                return
            cls = next(
                (
                    c
                    for c in application.registry("console.commands", list)
                    if command_name(c) == name
                ),
                None,
            )
            if cls is not None:
                await run_command_class_async(cls)
                return

    import asyncio

    def _dispatch() -> None:
        from arvel.console import build_cli

        build_cli()([name, *args], standalone_mode=False)

    await asyncio.get_running_loop().run_in_executor(None, _dispatch)


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
        """Schedule a console command by name (run via the CLI when due) — dispatched without
        blocking the scheduler's own event loop for the command's duration; see
        :func:`_dispatch_scheduled_command`."""

        async def _invoke() -> None:
            await _dispatch_scheduled_command(name, args)

        return self.call(_invoke)

    def due_events(self, moment: datetime) -> list[ScheduledEvent]:
        return [event for event in self.events if event.is_due(moment)]

    async def run_due(self, moment: datetime) -> None:
        """Run every due event **concurrently** (6.2a) — one tick's tasks no longer serialize
        behind each other, so a slow one doesn't delay a sibling due in the same minute. A failing
        event is LOGGED and skipped — one bad task must never starve the rest of the schedule (or
        kill the cron tick)."""
        import asyncio

        await asyncio.gather(*(self._run_one(event, moment) for event in self.due_events(moment)))

    @staticmethod
    async def _run_one(event: ScheduledEvent, moment: datetime) -> None:
        try:
            await event.run(moment)
        except Exception:
            from arvel.kernel.logging import LogManager

            LogManager().channel("schedule").error(
                "scheduled_task_failed",
                task=getattr(event.callback, "__name__", repr(event.callback)),
                exc_info=True,
            )
