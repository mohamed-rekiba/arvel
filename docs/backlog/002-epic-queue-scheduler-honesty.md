# Epic: Queue & Scheduler honesty fixes

## Summary

Three shipped APIs in `arvel.queue` and `arvel.scheduling` advertise Laravel-parity behaviour they don't deliver: `Bus.chain`/`Bus.batch` enqueue jobs independently while their docstrings promise sequential/stop-on-failure semantics; `queue:work` constructs a `Worker` without `QueueRestartSignal`, so `queue:restart` never takes effect; `ScheduledTask.in_maintenance_mode` and `ScheduledTask.output_to` are public DSL fields stored on the task but never read by `SchedulerKernel`. Greenfield rewrite — replace, don't deprecate.

## Audit reference

`messaging audit` (parallel review pass, 2026-06-05) — `[Critical Gaps]` section.

## Stories

### Story 1: `Bus.chain` either keeps its name and implements chain semantics, or is removed

**As a** queue-using developer, **I want** `Bus.chain([j1, j2, j3])` to either run jobs sequentially and stop on failure, or not exist at all, **so that** my code's behaviour matches the API surface I read.

**Acceptance Criteria**:
- [ ] Given `Bus.chain([j1, j2])`, when `j1` raises after dispatch, then `j2` is NOT enqueued / executed.
- [ ] Given `Bus.chain([j1, j2])`, when `j1` succeeds, then `j2` is enqueued only after `j1` finishes.
- [ ] Given `Bus.batch([j1, j2, j3])`, when called, then the jobs are dispatched fan-out and a `BatchId` is returned that callers can use to poll progress or attach `then`/`catch`/`finally` callbacks.
- [ ] If chain/batch semantics are not implemented, then both methods are removed from `Bus` and replaced by `Bus.dispatch_many(jobs)` whose docstring accurately says "fan-out, independent, fire-and-forget".
- [ ] Tests cover chain stop-on-failure, chain-on-success, batch progress, batch failure callback.

**Security Requirements**:
- [ ] None.

**Documentation Requirements**:
- [ ] `docs/site/docs/the-basics/queues.md` (or equivalent) section on chain/batch matches code 1:1.
- [ ] `arvel.queue.bus.Bus` docstrings match runtime behaviour exactly.

**Requirement Refs**: AUDIT-MSG-CRITICAL-1
**Priority**: Must
**Complexity**: Medium
**Status**: Ready

---

### Story 2: `queue:work` honors `queue:restart` via `QueueRestartSignal`

**As a** deployer, **I want** `queue:restart` to gracefully stop currently-running workers within the next poll, **so that** rolling deploys don't leave stale code running jobs.

**Acceptance Criteria**:
- [ ] Given a running `arvel queue:work`, when `arvel queue:restart` is issued, then the worker exits cleanly within `restart_check_interval` seconds (default 5).
- [ ] Given the worker process, when it boots, then `QueueWorkCommand` constructs `Worker` with a live `QueueRestartSignal` resolved from the cache / signal store.
- [ ] Given the worker reads the restart signal and finds a newer timestamp than its own start time, when it finishes the current job, then it exits with code 0 (graceful) rather than continuing to poll.
- [ ] Tests cover: cold start records baseline timestamp; restart signal flips timestamp; worker exits between jobs (NOT mid-job).

**Security Requirements**:
- [ ] None.

**Documentation Requirements**:
- [ ] `docs/site/docs/cli/commands.md` `queue:restart` entry notes the worker propagation window.

**Requirement Refs**: AUDIT-MSG-CRITICAL-2
**Priority**: Must
**Complexity**: Small
**Status**: Ready

---

### Story 3: `SchedulerKernel` honors `in_maintenance_mode` and `output_to`

**As a** sysadmin, **I want** `ScheduledTask.in_maintenance_mode()` and `outputTo(path)` to actually change behaviour, **so that** the public DSL isn't lying.

**Acceptance Criteria**:
- [ ] Given a task built with `.inMaintenanceMode()` and the app currently in maintenance mode, when the scheduler is due to run it, then the kernel skips invocation and logs `scheduled_task.skipped_maintenance` (or equivalent).
- [ ] Given a task built without `.inMaintenanceMode()` and the app in maintenance mode, when due, then the kernel skips it as well (current default — make this explicit and tested).
- [ ] Given a task with `.outputTo("storage/logs/foo.log")`, when it runs, then stdout/stderr from the invocation is appended to that file (relative to `app.base_path()`).
- [ ] Given an `outputTo` path that does not exist, when the task runs, then the parent dir is created with `parents=True, exist_ok=True`.
- [ ] Given `outputTo` writes fail (e.g., permission denied), when the task runs, then the failure is logged but the task is NOT marked failed (output is best-effort).
- [ ] Tests cover all four behaviours above and a regression test asserts the kernel reads both fields (greps `_invoke` for both attribute names).

**Security Requirements**:
- [ ] Path provided to `outputTo` is resolved against `app.base_path()`; absolute paths are accepted (CLI invoker is trusted, same as `openapi:export --output`).

**Documentation Requirements**:
- [ ] `docs/site/docs/digging-deeper/scheduling.md` (or equivalent) documents both modifiers as live.

**Requirement Refs**: AUDIT-MSG-CRITICAL-3
**Priority**: Must
**Complexity**: Small
**Status**: Ready

---

### Story 4: Silent fallback in `EventDispatcher._dispatch_queued` and `NotificationManager` is removed

**As a** developer, **I want** misconfigured queue/notification listeners to fail loudly during boot or first dispatch, **so that** production doesn't silently fall back to inline execution.

**Acceptance Criteria**:
- [ ] Given a `ShouldQueue` listener whose `Bus` resolution fails, when the event fires, then the dispatcher raises (or logs at ERROR with a clear "falling back to inline because <reason>" and exposes a config switch to disable the fallback in production).
- [ ] Given `NotificationManager` cannot resolve `Bus` for a `ShouldQueue` notification, then it raises (or logs at ERROR and falls back, gated by the same config switch).
- [ ] Default in `production` env: the fallback is disabled — misconfiguration fails fast.
- [ ] Tests cover both the loud-failure path (production) and the fallback-with-warning path (development).

**Security Requirements**:
- [ ] None.

**Documentation Requirements**:
- [ ] Configuration knob (`config/queue.py` or `config/events.py`) documented.

**Requirement Refs**: AUDIT-MSG-QUALITY-4
**Priority**: Should
**Complexity**: Small
**Status**: Ready

---

## Dependencies

- Story 1 → Story 4 (Bus contract feeds the notification/event paths).
- Stories 2 and 3 are independent.

## Notes

- Audit findings: `Bus.chain` `bus.py:42–45`; `Worker` signature `worker.py:68–72` vs command `queue_work.py:75`; `ScheduledTask` fields `scheduled_task.py:33–34` vs `SchedulerKernel._invoke` (never reads them).
- Greenfield: per `no-backward-compatibility.mdc`, rename / remove freely. If chain/batch semantics aren't going to be implemented, delete them; replace with `dispatch_many` with an honest docstring.
- Stage 4 (Validation) must include a grep that asserts every public method on `Bus` has its docstring match runtime behaviour.
