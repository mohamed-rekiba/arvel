# Epic: Worker cancellation propagates instead of failing the job

## Summary
The queue worker caught `asyncio.CancelledError` alongside normal exceptions, so cancelling a worker
(graceful shutdown, `SIGINT`, `task.cancel()`) was treated as a **job failure**: it counted a failed
attempt, re-queued or dead-lettered the in-flight job, and swallowed the cancellation (so the worker
didn't stop promptly). The worker now re-raises `CancelledError` and only treats real exceptions /
per-job timeouts as failures.

**Module:** queue · **Spec:** `docs/pipeline/specs/WI-arvel-008-worker-cancellation-contract.md`

## Stories

### Story 1: Cancelling a worker stops it cleanly without failing the job
**As an** operator, **I want** stopping a worker mid-job to stop the worker and leave the in-flight
job alone, **so that** deploys and shutdowns don't spuriously dead-letter healthy jobs.

**Acceptance Criteria**:
- [x] Given a worker running a job, when the worker task is cancelled, then `CancelledError` propagates and the worker stops (the cancellation is not swallowed).
- [x] Given that cancellation, then the job is not counted as a failed attempt and is not written to the dead-letter queue (`jobs_dead == 0`, `jobs_retried == 0`, DLQ empty).

**Security Requirements**:
- [x] None — control-flow correctness; no new surface.

**Documentation Requirements**:
- [x] `docs/site/docs/features/queues.md` notes that worker cancellation is not a job failure.

**Requirement Refs**: SPEC-1, SPEC-2
**Priority**: Must · **Complexity**: Small · **Status**: Done

### Story 2: Real failures and timeouts still fail correctly
**As an** application developer, **I want** genuine job errors and timeouts to keep retrying and
dead-lettering as before, **so that** the cancellation fix changes nothing about failure handling.

**Acceptance Criteria**:
- [x] Given a job whose `handle()` raises, when it runs, then it retries up to `tries` and then lands in the DLQ.
- [x] Given a job that exceeds its `timeout`, when it runs, then it fails via `TimeoutError` (logged as `queue.job.timeout`) and is retried/dead-lettered.

**Security Requirements**:
- [x] None.

**Documentation Requirements**:
- [x] Covered by existing retry/backoff and failed-jobs docs.

**Requirement Refs**: SPEC-3, SPEC-4
**Priority**: Must · **Complexity**: Small · **Status**: Done

## Dependencies
- None. Independent of WI-arvel-001..007.

## Notes
- A per-job timeout surfaces as `TimeoutError` on Python 3.11+ (verified on 3.14), so the old
  `CancelledError → TimeoutError` conversion in the DLQ branch was dead code and was removed.
- Deferred follow-ups (separate work items):
  - **F2 (Critical)** — database driver delete-on-pop / no visibility timeout (at-most-once on
    worker crash). Needs reserve + visibility timeout + reaper — a dedicated architectural WI.
  - **F3 (Medium)** — `Taskiq` driver `pop_blocking` ignores the poll timeout.
