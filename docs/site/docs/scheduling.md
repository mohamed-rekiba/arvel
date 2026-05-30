# Task Scheduling

For recurring work — sending the weekly digest, pruning expired sessions, cleaning up the audit log — Arvel ships an in-process scheduler. You define the schedule in Python; a single `arvel schedule:work` process triggers the work at the right cadence.

The advantage over plain cron: you keep the entire schedule **in version control**, expressed in code, with the same testing and review process as everything else.

## Defining the schedule

Schedules are defined in a `ServiceProvider`:

```python
from arvel.scheduling import Schedule


class ScheduleServiceProvider(ServiceProvider):
    async def boot(self) -> None:
        Schedule.command("digest:send-weekly").weekly().mondays().at("09:00")
        Schedule.job(PruneExpiredSessions()).every_hour()
        Schedule.call(self.cleanup_uploads).daily().at("02:30")

    async def cleanup_uploads(self) -> None:
        ...
```

Three kinds of scheduled tasks:

- **`command(name)`** — runs an Arvel CLI command (`uv run arvel <name>`).
- **`job(job)`** — dispatches a queued Job.
- **`call(callable)`** — calls an async function in-process.

## Frequencies

```python
Schedule.command("X").every_minute()
Schedule.command("X").every_five_minutes()
Schedule.command("X").every_fifteen_minutes()
Schedule.command("X").every_thirty_minutes()
Schedule.command("X").hourly()
Schedule.command("X").daily()
Schedule.command("X").daily_at("01:00")
Schedule.command("X").twice_daily(1, 13)
Schedule.command("X").weekly()
Schedule.command("X").weekly_on(1, "08:00")     # Monday 08:00
Schedule.command("X").monthly()
Schedule.command("X").quarterly()
Schedule.command("X").yearly()
Schedule.command("X").cron("*/5 * * * *")        # raw cron
```

## Constraints

```python
Schedule.command("X").daily()
    .timezone("America/New_York")
    .when(lambda: feature_flag("nightly-job"))
    .skip(lambda: holiday_today())
    .name("nightly-X")
    .without_overlapping()
    .on_one_server()
```

| Constraint | Effect |
|---|---|
| `.timezone(...)` | Evaluate the schedule in this timezone |
| `.when(callable)` | Run only when the callable returns truthy |
| `.skip(callable)` | Skip when the callable returns truthy |
| `.without_overlapping()` | Don't start a new run while the previous is in-flight |
| `.on_one_server()` | When running multiple scheduler processes, only one runs the task |
| `.name(...)` | Human-readable label for logs |

## Running the scheduler

For long-lived deployments, run the scheduler as a dedicated process:

```bash
uv run arvel schedule:work
```

For containerized or serverless deployments where you want to delegate timing to cron, run the scheduler in one-shot mode:

```cron
* * * * * cd /var/www/myapp && uv run arvel schedule:work --once >> /dev/null 2>&1
```

`schedule:work --once` fires any due tasks immediately, then exits. Without `--once`, `schedule:work` is a long-running process that loops every minute (configurable with `--sleep`).

## Hooks and output capture

```python
Schedule.command("backup:run").daily_at("03:00")
    .on_success(lambda: Log.info("backup.ok"))
    .on_failure(lambda: Notification.route("mail", "ops@example.com").notify(BackupFailed()))
    .send_output_to("storage/logs/backup.log")
```

## Listing scheduled tasks

```bash
uv run arvel schedule:list
```

Outputs every registered task with frequency, name, constraints, and next-run timestamp.

## Controlling the scheduler

When `schedule:work` is running as a long-lived process you can send it control signals without restarting it. All three commands write a marker to the configured cache store; the loop polls for them at each tick boundary.

```bash
uv run arvel schedule:interrupt   # tell the loop to exit cleanly at the next tick
uv run arvel schedule:pause       # suspend task dispatch (loop keeps running)
uv run arvel schedule:continue    # resume after schedule:pause
```

**Prerequisites**: a cache store must be configured (`CACHE_DEFAULT=redis` or `database`). The markers are written with a 120-second TTL so a crash doesn't leave a stale interrupt marker. If no cache is bound the commands degrade gracefully — the loop won't receive the signal.

**Typical workflow for a hot deploy**:

```bash
uv run arvel schedule:pause       # stop dispatching while the deploy runs
# ... deploy code changes ...
uv run arvel schedule:continue    # resume
```

For a scheduled process that you want to exit cleanly (so your supervisor can restart it):

```bash
uv run arvel schedule:interrupt   # loop exits at its next tick
```

## Where to next?

- [Queues](queues.md) — what `Schedule.job(...)` dispatches into.
- [Configuration](configuration.md) — env vars for scheduler timezone.
- [Deployment](deployment.md) — running the scheduler in production.
