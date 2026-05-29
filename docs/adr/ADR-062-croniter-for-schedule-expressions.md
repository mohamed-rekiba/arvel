# ADR-062 — Use `croniter` for scheduler expression parsing

**Status**: Accepted
**Date**: 2026-05-19
**Decider**: Solution Architect
**Supersedes**: none
**Related**: PRD-015 § 10 Q1, SAD-015 § 3

---

## Context

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

## Decision

Use **`croniter>=6.0.0`** as a runtime dependency. It lands in
`packages/arvel/pyproject.toml` `[project.dependencies]` (not opt-in extra),
because the scheduler is part of the framework not a swappable extension.

## Rationale

- **No transitive runtime deps** — `pip install croniter` adds only croniter.
- **Pure-Python** — installs everywhere arvel runs (no C extension build).
- **MIT-licensed** — same as arvel.
- **Battle-tested** — used by Airflow (>30k stars), Celery Beat, dbt-cron.
- **Right surface** — exposes `croniter.croniter(expression, base=now, ret_type=datetime)` and `.get_next()` / `.get_prev()` / `.is_valid(expr)`. Maps directly onto our `ScheduledTask.expression` field.
- **Timezone-aware via stdlib `zoneinfo`** — we pass `croniter(..., tz=ZoneInfo(task.timezone))`. No new TZ database.

## Consequences

### Positive

- We don't write or maintain cron parsing code.
- Validation at registration time is free: `croniter.is_valid(expression)` either returns True or we raise `ScheduleError`.
- Timezone behavior is well-documented and matches Laravel's expectation (a task scheduled `0 9 * * *` in `Europe/Paris` fires at 09:00 Paris time year-round, handling DST).

### Negative

- One more runtime dep to audit on each release (mitigated: the dep is stable; CVE history clean).
- `croniter` exposes some legacy 7-field "with-year" syntax we don't want users using. We document only 5-field; a wide-open parser is a small foot-gun.

### Neutral

- We pin `>=6.0.0` (not `>=6.0.0,<7.0.0`) — `croniter` follows SemVer and breaking changes are rare. WI-017 hardening will revisit upper-bound pinning policy framework-wide.

## Alternatives rejected

- **`APScheduler`** — too much. We need a parser, not a scheduling framework.
- **Hand-rolled** — leap-year and DST corner cases are too easy to get wrong; not worth 300 LoC of bespoke code.
- **`cronex`** — abandoned (last release 2014).
- **`celery_beat.schedules.crontab`** — pulls in all of Celery as a runtime dep. No.

## Implementation notes (for Stage 3b)

```python
# packages/arvel/src/arvel/scheduling/expressions.py
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

## Cross-references

- SAD-015 § 3 Q1
- PRD-015 § 10 Q1
- Constitution Article II (typed interfaces — TZ types are stdlib `zoneinfo.ZoneInfo`)
