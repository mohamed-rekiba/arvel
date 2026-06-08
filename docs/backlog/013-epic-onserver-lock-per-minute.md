# Epic: onOneServer election lock is per-execution

## Summary
`SchedulerKernel` built the `onOneServer` election lock with a time-less key
(`scheduler:onserver:{task.name}`) and relied on TTL expiry to clear it. Unlike Laravel
— which keys the server mutex per scheduled minute (`mutexName().format('Hi')`) — the
static key meant the lock acquired in one minute kept every server blocked until its TTL
expired. Any task whose TTL ≥ its run interval fired once and then went dark (silent
missed executions on every server). The election key now folds in the due minute, so it
dedupes servers within a minute but never blocks the next run.

**Module:** scheduling · **Spec:** `docs/pipeline/specs/WI-arvel-013-onserver-lock-per-minute.md`

## Stories

### Story 1: An onOneServer task keeps firing on schedule
**As an** operator running a multi-server deployment, **I want** an `onOneServer` task to
run every due minute, **so that** opting into single-server execution doesn't silently
stop the task after its first run.

**Acceptance Criteria**:
- [x] Given an `everyMinute().onOneServer(ttl_seconds=120)` task, when three consecutive minutes elapse, then it runs 3× (lock rotates per minute).
- [x] Given two servers ticking in the same minute, when both evaluate the task, then exactly one runs.
- [x] Given the existing single-minute two-server election, when both tick, then exactly one wins (no regression).

**Security Requirements**:
- [x] None (no change to auth or signing; lock semantics only).

**Documentation Requirements**:
- [x] `docs/site/docs/features/scheduling.md` explains the per-minute election scope and the shared-cache requirement.

**Requirement Refs**: SPEC-1, SPEC-2, SPEC-3
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- None. Independent of WI-arvel-001..012.

## Notes
- `withoutOverlapping` (the long-lived concurrency guard) is intentionally keyed by task
  name and released in `finally` — unchanged.
- Folded-in cleanup: the Module 11 session-middleware regression test reached into
  `ArraySessionStore._store`; switched to the public async `store.read(...)` API to keep
  the full-suite pyright gate clean.
- Deferred follow-ups (separate work items):
  - **Builder frequency/constraint sugar** — `twiceDaily`, `weekdays`/`weekends`, named
    days, `quarterly`, `->between()`, `->when()/->skip()`, `->before()/->after()` hooks.
  - **Tick drift vs OS cron** — fixed-interval sleep can skip a minute beyond the
    1-minute `is_due` tolerance; design tradeoff of the in-process loop.
