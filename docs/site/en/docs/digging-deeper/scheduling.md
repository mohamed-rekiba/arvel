# Scheduling

Cron entries scattered across servers are hard to reason about. Arvel’s **`Scheduler`** keeps recurring work **in code**: you register **`ScheduleEntry`** objects against job classes, evaluate cron expressions, and dispatch due work through **`QueueContract`**—same pattern as Laravel’s task scheduler, with fluent helpers for common intervals.

Expressions use **five-field cron** semantics (minute, hour, day of month, month, day of week), validated through **`croniter`**.

## Building schedules

Create a **`Scheduler`** with a queue and optional lock backend for overlap protection, then call **`scheduler.job(MyJob)`** to get a **`ScheduleEntry`** and chain methods:

```python
from arvel.queue.job import Job
from arvel.scheduler.scheduler import Scheduler


class SendReminders(Job):
    async def handle(self) -> None: ...


def register_schedule(scheduler: Scheduler) -> None:
    (
        scheduler
        .job(SendReminders)
        .daily_at("08:30")
        .timezone("America/New_York")
        .when(lambda: not is_holiday())
    )
```

**`ScheduleEntry`** includes helpers like **`every_minute`**, **`hourly`**, **`daily`**, **`weekly`**, **`monthly`**, and **`cron("*/15 * * * *")`** for full control. Use **`when`** and **`skip`** for conditional execution, and **`without_overlapping`** to avoid stacking runs when a previous job is still working.

## Time zones

**`timezone("Region/City")`** ensures **`is_due`** compares the cron against local wall time, then dispatches—critical for “every day at 9am” style entries that cross DST boundaries.

## Running the scheduler

The **`arvel schedule`** CLI loads your app’s `schedule.py` (if present), constructs the scheduler, and either **runs once** or runs a **daemon loop** with a configurable sleep interval. Production often uses **cron** or a supervisor to invoke `schedule run` every minute—just like Laravel’s `schedule:run`.

## Mental model

The scheduler answers **when**; the queue answers **how work executes**. Keep scheduled jobs **small and idempotent** where possible, push heavy lifting into **`Job.handle`**, and let overlap locks save you from accidental double sends.

That combination—expressive entries, cron validation, queue integration—is what makes scheduled tasks feel **maintainable** instead of mysterious.
