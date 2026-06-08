# WI-arvel-013 — onOneServer election lock must be per-execution

| | |
|---|---|
| **Module** | scheduling |
| **Complexity** | L2 | **Risk** | Tier 2 | **Data** | internal |
| **Autonomous** | yes | **Frontend** | no |
| **Research** | `.context/research/013-scheduling.md` (C1 fixed; builder frequency/constraint sugar, tick-drift-vs-cron deferred) |
| **Review** | C1 confirmed: static election key bleeds across minutes; any TTL ≥ run interval silently drops every run after the first |

## Problem

`SchedulerKernel._run_one` built the `onOneServer` election lock with a time-less key
and relied on TTL expiry to clear it:

```python
if task.on_one_server and self._cache is not None:
    lock = self._cache.lock(
        f"scheduler:onserver:{task.name}", ttl=task.on_one_server_ttl_seconds
    )
    if not await lock.acquire():
        outcomes.append(TaskOutcome.skip(task.name, "not_one_server_winner"))
        return
```

Laravel keys the server mutex per scheduled minute (`mutexName().format('Hi')`,
`CacheSchedulingMutex::create`), so each execution gets a fresh key and the previous
one only blocks the *same* minute. With the static key, the lock acquired in minute N
keeps every server blocked until its TTL expires. A task whose TTL ≥ its run interval
fires once and then goes dark — silent missed executions on **every** server. The
default `onOneServer(ttl_seconds=60)` on an `everyMinute()` task is already borderline.

Reproduced deterministically: `everyMinute().onOneServer(ttl_seconds=120)` over three
consecutive minutes ran **1×** instead of **3×**.

## Spec Items → Verification

| ID | Spec item | Test | Status |
|---|---|---|---|
| SPEC-1 | An `onOneServer` task with TTL ≥ its interval fires every due minute (lock rotates per minute). | `tests/scheduling/test_scheduler_kernel.py::TestOnOneServer::test_lock_rotates_per_minute` | PASS |
| SPEC-2 | Two servers ticking in the same minute still elect exactly one winner. | `...::TestOnOneServer::test_two_servers_same_minute_still_elect_one_winner` | PASS |
| SPEC-3 | Existing single-minute two-server election unchanged. | `...::TestOnOneServer::test_two_servers_only_one_wins` | PASS |
| SPEC-4 (X-cut: types/lint) | mypy `--strict` + pyright clean; ruff clean; scheduling suite (56) + full framework suite (4306) green. | `mypy` + `pyright` + `ruff` + `pytest` | PASS |

## Root-cause fix

`kernel.py` — thread the tick's `now` into `_run_one` and fold the due minute
(`now.strftime("%Y%m%d%H%M")`) into the election key:
`f"scheduler:onserver:{task.name}:{slot}"`. The lock now rotates every minute like
Laravel, so it dedupes servers within a minute but never blocks the next execution
regardless of TTL. The lock is still never released (TTL-expiry cleanup), matching
Laravel. `withoutOverlapping` (the long-lived concurrency guard) is unchanged — it is
intentionally keyed by task name and released in `finally`.

## Deliberate design decisions

- **Per-minute slot, not per-tick UUID.** All servers ticking in the same minute must
  compute the *same* key to contend, so the slot is the shared due minute — exactly
  Laravel's `format('Hi')` semantics (with date prefix to avoid cross-day reuse).
- **Keep "never release".** Like Laravel, the election lock isn't released; it expires.
  With a rotating key a stale lock can't outlive its minute, so TTL only needs to cover
  the spread of server ticks within a minute (the default 60 s is ample).

## Out-of-scope cleanup (folded in)

- `tests/session/test_middleware.py` — the Module 11 regression test reached into
  `ArraySessionStore._store` (pyright `reportPrivateUsage`). Switched to the public
  async `store.read(...)` API so the full-suite pyright gate stays clean.

## Deferred (tracked)

- **Builder frequency/constraint sugar** — `twiceDaily`, `weekdays`/`weekends`, named
  days, `quarterly`, `->between()/->unlessBetween()`, `->when()/->skip()` filters,
  `->before()/->after()` hooks, `->emailOutputTo()`. Parity-additive; no defect.
- **Tick drift vs OS cron** — `serve_forever` sleeps a fixed interval rather than
  aligning to the minute boundary, so a slow tick can skip a minute beyond the
  1-minute `is_due` tolerance. Design tradeoff inherent to the in-process loop.
