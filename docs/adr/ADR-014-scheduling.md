# ADR-014 — Scheduling

**Status**: Accepted
**Date**: original decisions 2026-05-19 – 2026-05-19; merged into one ADR on 2026-06-07 during the WI-arvel-005 consolidation pass
**Scope**: croniter for schedule expressions, asyncio.TaskGroup for scheduler concurrency.

## Why this is one ADR

Two decisions, same scheduler. Reading both at once is the only way to see why the scheduler is what it is.

---

## § 1 — Use `croniter` for scheduler expression parsing

**Originally**: ADR-113 · Date: 2026-05-19

### Context

WI-015's scheduler (15-S1) needs a cron-expression parser to evaluate which
registered tasks are due at a given `datetime`. Three real candidates exist
in the Python ecosystem:

- **`croniter`** — pure-Python, MIT, ~2009-vintage, used by Apache Airflow,
  Celery Beat, dbt-cron. No transitive runtime deps. `>=6.0.0` supports
  6-field (with seconds), 7-field (with years), and timezone-aware
  evaluation. Returns next/previous scheduled times relative to a base time.
- **`apscheduler.triggers.cron`** — comes bundled inside the `APScheduler`
  package, which pulls in a whole scheduling framework we'd be re-implementing
  on top of. Heavy. ~50k LoC.
- **Hand-rolled** — implementing a 5/6/7-field cron evaluator from scratch.
  ~300 LoC of bit-twiddling plus an edge-case minefield (leap years, DST
  transitions, week-vs-day-of-month conflict semantics).

### Decision

Use **`croniter>=6.0.0`** as a runtime dependency. It lands in
`packages/arvel/pyproject.toml` `[project.dependencies]` (not opt-in extra),
because the scheduler is part of the framework not a swappable extension.

### Rationale

- **No transitive runtime deps** — `pip install croniter` adds only croniter.
- **Pure-Python** — installs everywhere arvel runs (no C extension build).
- **MIT-licensed** — same as arvel.
- **Battle-tested** — used by Airflow (>30k stars), Celery Beat, dbt-cron.
- **Right surface** — exposes `croniter.croniter(expression, base=now, ret_type=datetime)` and `.get_next()` / `.get_prev()` / `.is_valid(expr)`. Maps directly onto our `ScheduledTask.expression` field.
- **Timezone-aware via stdlib `zoneinfo`** — we pass `croniter(..., tz=ZoneInfo(task.timezone))`. No new TZ database.

### Consequences

#### Positive

- We don't write or maintain cron parsing code.
- Validation at registration time is free: `croniter.is_valid(expression)` either returns True or we raise `ScheduleError`.
- Timezone behavior is well-documented and matches Laravel's expectation (a task scheduled `0 9 * * *` in `Europe/Paris` fires at 09:00 Paris time year-round, handling DST).

#### Negative

- One more runtime dep to audit on each release (mitigated: the dep is stable; CVE history clean).
- `croniter` exposes some legacy 7-field "with-year" syntax we don't want users using. We document only 5-field; a wide-open parser is a small foot-gun.

#### Neutral

- We pin `>=6.0.0` (not `>=6.0.0,<7.0.0`) — `croniter` follows SemVer and breaking changes are rare. WI-017 hardening will revisit upper-bound pinning policy framework-wide.

### Alternatives rejected

- **`APScheduler`** — too much. We need a parser, not a scheduling framework.
- **Hand-rolled** — leap-year and DST corner cases are too easy to get wrong; not worth 300 LoC of bespoke code.
- **`cronex`** — abandoned (last release 2014).
- **`celery_beat.schedules.crontab`** — pulls in all of Celery as a runtime dep. No.

### Implementation notes (for Stage 3b)

```python
## packages/arvel/src/arvel/scheduling/expressions.py
from datetime import datetime
from zoneinfo import ZoneInfo
from croniter import croniter

def is_valid_expression(expression: str) -> bool:
    return croniter.is_valid(expression)

def next_run_after(expression: str, *, base: datetime, timezone: str) -> datetime:
    base_aware = base.astimezone(ZoneInfo(timezone))
    it = croniter(expression, base_aware)
    return it.get_next(datetime)

def is_due(expression: str, *, now: datetime, timezone: str, tolerance_seconds: int = 1) -> bool:
    now_aware = now.astimezone(ZoneInfo(timezone))
    prev = croniter(expression, now_aware).get_prev(datetime)
    return (now_aware - prev).total_seconds() < tolerance_seconds
```

### Cross-references

- SAD-015 § 3 Q1
- PRD-015 § 10 Q1
- Constitution Article II (typed interfaces — TZ types are stdlib `zoneinfo.ZoneInfo`)

---

## § 2 — Use `asyncio.TaskGroup` for scheduler concurrency

**Originally**: ADR-114 · Date: 2026-05-19

### Context

`SchedulerKernel.run_due_tasks(now)` evaluates registered tasks against the
current `datetime` and dispatches the due ones. Three concurrency primitives
exist in Python 3.14 stdlib:

- **`asyncio.gather(*coros)`** — returns when ALL coros complete; on
  exception in any coro, the others are not cancelled by default.
- **`asyncio.TaskGroup`** (PEP 654, Python 3.11+) — context manager;
  cancels sibling tasks if any task raises; propagates as an `ExceptionGroup`.
- **Sequential `await` in a loop** — no concurrency; slow when N tasks fan out.

### Decision

Use **`asyncio.TaskGroup`** for dispatching the per-task coroutines inside
`run_due_tasks(now)`. Per-task exceptions are caught BEFORE they reach the
TaskGroup boundary (the per-task try/except wraps the callback in a recorder
that converts the exception to a `TaskOutcome.failed(reason=...)` record).

The TaskGroup therefore never sees an exception in normal operation; it's
chosen for its **bounded concurrency semantics and clean cancellation on
KeyboardInterrupt** (Ctrl-C in `schedule:work` cleanly cancels in-flight
tasks instead of dangling them).

### Rationale

- **Right for our concurrency model** — we want bounded structured concurrency
  (a single tick fans out to N concurrent tasks, all must observe completion
  before the next tick).
- **Clean cancellation semantics** — `Ctrl-C` propagates as
  `KeyboardInterrupt` → `asyncio.CancelledError` to all in-flight tasks
  via the TaskGroup's exit; no orphaned coroutines.
- **Python 3.14+ everywhere** — we already require 3.14+ per the project
  pyproject.toml. No backport-compatibility concerns.
- **PEP 654 ExceptionGroup** — even if a per-task except handler misses a
  case, the resulting ExceptionGroup is easy to inspect (`eg.exceptions` is
  a tuple, each tagged with its task name via `__notes__`).

### Consequences

#### Positive

- Structured concurrency: no detached tasks; no resource leaks.
- Clean Ctrl-C handling in `schedule:work` (cancels in-flight tasks immediately, no orphans).
- Per-task semantics map naturally to `async with TaskGroup() as tg: tg.create_task(...)`.

#### Negative

- `TaskGroup` requires Python 3.11+. We're 3.14+, so no concern.
- Bounded concurrency via TaskGroup requires us to add our own semaphore
  (`max_concurrency=16` default). We use `asyncio.Semaphore` inside each
  task's coroutine — small adapter, ~5 LOC.

#### Neutral

- We don't expose TaskGroup to consumers; it's a private implementation
  detail of `SchedulerKernel.run_due_tasks`.

### Alternatives rejected

- **`asyncio.gather`** — looser exception semantics; on a per-task crash, sibling tasks aren't cancelled (we want this safety net). Also less Pythonic in 3.11+ where TaskGroup exists.
- **Sequential `await`** — when N=100 tasks fan out, the last task waits for the first 99 to finish. Not acceptable for our use case (scheduled tasks should be independent).
- **`anyio.create_task_group`** — anyio is already a transitive dep but not a direct one; using stdlib `asyncio.TaskGroup` keeps the framework's "stdlib-first" posture.

### Implementation notes (for Stage 3b)

```python
## packages/arvel/src/arvel/scheduling/kernel.py
from datetime import datetime
import asyncio

class SchedulerKernel:
    def __init__(
        self,
        schedule: Schedule,
        lock_manager: LockManager,
        log_manager: LogManager,
        *,
        max_concurrency: int = 16,
    ) -> None:
        self._schedule = schedule
        self._locks = lock_manager
        self._log = log_manager
        self._sem = asyncio.Semaphore(max_concurrency)

    async def run_due_tasks(self, now: datetime) -> SchedulerRunResult:
        due = [t for t in self._schedule.tasks() if t.is_due(now)]
        outcomes: list[TaskOutcome] = []

        async with asyncio.TaskGroup() as tg:
            for task in due:
                tg.create_task(self._run_one(task, outcomes))

        return SchedulerRunResult(outcomes=tuple(outcomes), evaluated_at=now)

    async def _run_one(self, task: ScheduledTask, outcomes: list[TaskOutcome]) -> None:
        async with self._sem:
            try:
                await self._lock_and_run(task)
                outcomes.append(TaskOutcome.success(task.name))
            except Exception as e:  # noqa: BLE001 — explicit blanket catch
                self._log.channel("scheduler").error(
                    "scheduler.task.failed",
                    task_name=task.name,
                    exception_type=type(e).__name__,
                    traceback=traceback.format_exc(),
                )
                outcomes.append(TaskOutcome.failure(task.name, reason=str(e)))
```

### Cross-references

- SAD-015 § 3 Q3
- PRD-015 § 10 Q3, AC for US-015-04, NFR-015-005
- Constitution Article II (typed interfaces)
- Reused infra: `arvel.cache.lock.LockManager` (WI-006)

---

## Subsumes

This ADR absorbs the following ADRs in the WI-arvel-005 consolidation pass (2026-06-07). The original files are deleted; their decision text is preserved verbatim above in the corresponding `§` sections.

| Old | Date | Subject | New location |
|---|---|---|---|
| ADR-113 | 2026-05-19 | Use `croniter` for scheduler expression parsing | § 1 |
| ADR-114 | 2026-05-19 | Use `asyncio.TaskGroup` for scheduler concurrency | § 2 |
