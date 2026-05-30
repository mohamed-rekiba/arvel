# ADR-064 — Use `asyncio.TaskGroup` for scheduler concurrency

**Status**: Accepted
**Date**: 2026-05-19
**Decider**: Solution Architect
**Supersedes**: none
**Related**: PRD-015 § 10 Q3, SAD-015 § 3

---

## Context

`SchedulerKernel.run_due_tasks(now)` evaluates registered tasks against the
current `datetime` and dispatches the due ones. Three concurrency primitives
exist in Python 3.14 stdlib:

- **`asyncio.gather(*coros)`** — returns when ALL coros complete; on
  exception in any coro, the others are not cancelled by default.
- **`asyncio.TaskGroup`** (PEP 654, Python 3.11+) — context manager;
  cancels sibling tasks if any task raises; propagates as an `ExceptionGroup`.
- **Sequential `await` in a loop** — no concurrency; slow when N tasks fan out.

## Decision

Use **`asyncio.TaskGroup`** for dispatching the per-task coroutines inside
`run_due_tasks(now)`. Per-task exceptions are caught BEFORE they reach the
TaskGroup boundary (the per-task try/except wraps the callback in a recorder
that converts the exception to a `TaskOutcome.failed(reason=...)` record).

The TaskGroup therefore never sees an exception in normal operation; it's
chosen for its **bounded concurrency semantics and clean cancellation on
KeyboardInterrupt** (Ctrl-C in `schedule:work` cleanly cancels in-flight
tasks instead of dangling them).

## Rationale

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

## Consequences

### Positive

- Structured concurrency: no detached tasks; no resource leaks.
- Clean Ctrl-C handling in `schedule:work` (cancels in-flight tasks immediately, no orphans).
- Per-task semantics map naturally to `async with TaskGroup() as tg: tg.create_task(...)`.

### Negative

- `TaskGroup` requires Python 3.11+. We're 3.14+, so no concern.
- Bounded concurrency via TaskGroup requires us to add our own semaphore
  (`max_concurrency=16` default). We use `asyncio.Semaphore` inside each
  task's coroutine — small adapter, ~5 LOC.

### Neutral

- We don't expose TaskGroup to consumers; it's a private implementation
  detail of `SchedulerKernel.run_due_tasks`.

## Alternatives rejected

- **`asyncio.gather`** — looser exception semantics; on a per-task crash, sibling tasks aren't cancelled (we want this safety net). Also less Pythonic in 3.11+ where TaskGroup exists.
- **Sequential `await`** — when N=100 tasks fan out, the last task waits for the first 99 to finish. Not acceptable for our use case (scheduled tasks should be independent).
- **`anyio.create_task_group`** — anyio is already a transitive dep but not a direct one; using stdlib `asyncio.TaskGroup` keeps the framework's "stdlib-first" posture.

## Implementation notes (for Stage 3b)

```python
# packages/arvel/src/arvel/scheduling/kernel.py
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

## Cross-references

- SAD-015 § 3 Q3
- PRD-015 § 10 Q3, AC for US-015-04, NFR-015-005
- Constitution Article II (typed interfaces)
- Reused infra: `arvel.cache.lock.LockManager` (WI-006)
