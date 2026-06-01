# Task Scheduling

<a name="introduction"></a>
## Introduction

In the past, you may have written a cron entry for each task you needed to schedule. Arvel's command scheduler offers a fresh approach: you define your task schedule in code with a fluent, readable API, and a single long-running process executes due tasks. You only need one cron entry on your server — to keep that process alive.

<a name="registering-the-provider"></a>
## Registering the Provider

Scheduling is wired in automatically — `SchedulerServiceProvider` is one of the framework's baseline providers, so there's nothing to add to `bootstrap/providers.py`. It binds the `Schedule` as a container singleton, registers the scheduler CLI commands, and auto-discovers `app/console/kernel.py`.

> [!NOTE]
> `Schedule` is a container singleton, not a facade. Define tasks by implementing a `schedule(self, schedule)` method on a `Kernel` class in `app/console/kernel.py` — the provider discovers and calls it on boot.

<a name="defining-schedules"></a>
## Defining Schedules

Define your tasks in the console kernel:

```python
from arvel.scheduling import Schedule


class Kernel:
    def schedule(self, schedule: Schedule) -> None:
        schedule.call(self.prune_old_records).daily()
        schedule.job(GenerateReports).dailyAt("02:00")
        schedule.command("cache:clear").hourly()

    async def prune_old_records(self) -> None:
        ...
```

<a name="scheduling-callbacks"></a>
### Scheduling Callbacks

`schedule.call()` schedules an async callable:

```python
schedule.call(prune_old_records).everyFifteenMinutes()
```

<a name="scheduling-jobs-and-commands"></a>
### Scheduling Jobs & Commands

`schedule.job()` dispatches a [queued job](queues.md); `schedule.command()` runs a [console command](../cli/commands.md) by name:

```python
schedule.job(GenerateReports).daily()
schedule.command("queue:flush").weeklyOn(0, "03:00")
```

> [!NOTE]
> `schedule.job(...)` needs `QueueServiceProvider` bound to dispatch, and `schedule.command(...)` needs the console application (`ConsoleServiceProvider`). When the dependency isn't registered, the scheduler skips that task rather than failing.

<a name="schedule-frequency-options"></a>
## Schedule Frequency Options

Each `call`/`job`/`command` returns a builder with chainable frequency methods:

| Method | Cron equivalent |
|---|---|
| `everyMinute()` | `* * * * *` |
| `everyFiveMinutes()` | `*/5 * * * *` |
| `everyTenMinutes()` | `*/10 * * * *` |
| `everyFifteenMinutes()` | `*/15 * * * *` |
| `everyThirtyMinutes()` | `*/30 * * * *` |
| `hourly()` | `0 * * * *` |
| `daily()` | `0 0 * * *` |
| `dailyAt("13:30")` | `30 13 * * *` |
| `weeklyOn(day, "HH:MM")` | day `0`–`6` (0=Sun) |
| `monthly()` | `0 0 1 * *` |
| `monthlyOn(day, "HH:MM")` | day `1`–`31` |
| `yearly()` | `0 0 1 1 *` |
| `cron("...")` | a raw expression |

Set the timezone for a task with `.timezone("Europe/Paris")` (the default is UTC).

<a name="preventing-task-overlaps"></a>
## Preventing Task Overlaps

If a task runs long, the next tick could start a second copy. `withoutOverlapping()` prevents that — the second run is skipped until the first finishes (or the TTL expires):

```python
schedule.call(generate_report).everyFiveMinutes().withoutOverlapping()
```

For multi-server deployments, `onOneServer()` ensures only one server runs a given task per tick.

<a name="running-the-scheduler"></a>
## Running the Scheduler

Run the long-lived scheduler process; it wakes each minute and runs whatever is due:

```bash
arvel schedule:work
arvel schedule:list      # list registered tasks
```

> [!NOTE]
> The control commands `schedule:interrupt`, `schedule:pause`, and `schedule:continue` signal the running scheduler through cache markers, and `schedule:work` honors them. They require `CacheServiceProvider` — without a bound cache the signals are no-ops.
