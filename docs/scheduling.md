# Task Scheduling

In the past you might have written a cron entry for each recurring task on your server. This quickly
gets painful — the schedule lives outside source control and each change means SSHing in. arvel's
command scheduler lets you define your recurring tasks **in code**, and needs only a single cron entry
on the server.

## Defining schedules

Define scheduled tasks in `app/routes/console.py` using the `Schedule` entry point:

```python
# app/routes/console.py
from arvel import Schedule

Schedule.command("queue:work --stop-when-empty").hourly()
Schedule.call(prune_old_exports).daily_at("02:00")
```

You can schedule three kinds of work:

```python
Schedule.call(callback)               # an async/sync callable
Schedule.command("cache:clear")       # an arvel console command by signature
Schedule.job(SendDigest())            # a queued job (see Queues)
```

### Frequency options

Chain a frequency onto any scheduled task:

| Method | Runs the task... |
|--------|------------------|
| `.every_minute()` | every minute |
| `.hourly()` | every hour |
| `.daily()` | every day at midnight |
| `.daily_at("13:00")` | every day at a given time |
| `.twice_daily(1, 13)` | at two hours each day |
| `.weekly()` / `.monthly()` / `.quarterly()` / `.yearly()` | at the start of the period |
| `.weekdays()` / `.weekends()` | constrain to those days |
| `.cron("*/5 * * * *")` | a raw cron expression |

Constraints compose — `.daily().weekdays().between("9:00", "17:00")` runs at midnight only on a weekday
within business hours. Set the evaluation timezone with `.timezone("America/New_York")`.

### Truth-test & environment constraints

```python
Schedule.command("report:send").daily().when(lambda: billing_enabled())
Schedule.command("report:send").daily().skip(lambda: holiday_today())
Schedule.command("report:send").daily().environments("production")
```

## Preventing task overlaps

By default a task runs even if its previous run is still going. Guard long tasks so they never overlap:

```python
Schedule.command("report:generate").hourly().without_overlapping()
```

On a multi-server deployment, ensure a task runs on **one** server only:

```python
Schedule.command("report:generate").daily().on_one_server()
```

Both use a cache lock, so they need a shared [cache](cache.md) store.

### Task hooks

```python
Schedule.command("backup:run").daily() \
    .before(notify_start) \
    .after(notify_done) \
    .on_success(record_ok) \
    .on_failure(alert)
```

## Running the scheduler

The scheduler itself is driven by one cron entry that invokes `schedule:run` every minute; it works
out which tasks are actually due:

```cron
* * * * * cd /path-to-app && arvel schedule:run >> /dev/null 2>&1
```

## See also

- [Console](console.md) — the commands you schedule with `Schedule.command(...)`.
- [Queues](queues.md) — `Schedule.job(...)` dispatches onto a queue.
- [Cache](cache.md) — backs `without_overlapping()` and `on_one_server()`.
