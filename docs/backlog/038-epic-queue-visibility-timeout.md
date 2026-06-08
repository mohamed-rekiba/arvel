# Epic: Database queue must not lose jobs when a worker crashes

## Summary
The database queue driver deleted jobs on pop, so a worker that died mid-handle lost the
job permanently. Switch to Laravel's reserve-then-ack model: pop reserves the row, the
worker deletes it on completion, and a reservation that's never acked redelivers after a
visibility timeout (`retry_after`).

**Module:** queue · **Spec:** `docs/pipeline/specs/WI-arvel-038-queue-visibility-timeout.md`

## Stories

### Story 1: A crashed worker's job redelivers
**As an** operator running database-queued jobs, **I want** a job whose worker crashed
mid-handle to run again, **so that** an OOM or node loss doesn't silently drop work.

**Acceptance Criteria**:
- [ ] Given a job is popped, when no `delete_reserved` follows, then the row stays in the table reserved.
- [ ] Given a reserved row, when a second worker polls before `retry_after`, then it is not handed out again.
- [ ] Given a reserved row, when `retry_after` has elapsed, then the next poll redelivers it.
- [ ] Given a job finishes (success, retry, or DLQ), when the worker acks, then the row is deleted.

### Story 2: Configurable visibility timeout
**As an** operator with long-running jobs, **I want** to tune the visibility timeout,
**so that** a slow job isn't redelivered and run twice while still in flight.

**Acceptance Criteria**:
- [ ] `QUEUE_DATABASE_RETRY_AFTER` sets the timeout; default is 90s.
- [ ] Redis/taskiq/sync drivers are unaffected (no reservation semantics).

**Security Requirements**:
- [ ] Malformed payloads and unknown job classes are deleted, not left reserved forever (no unbounded growth / poison-row buildup).

**Requirement Refs**: SPEC-1
**Priority**: Must · **Complexity**: Medium · **Status**: Done

## Dependencies
- Builds on WI-008 (worker cancellation re-pushes the in-flight job).
- Adds `reserved_at` to the `jobs` table migration.

## Notes
- At-least-once delivery: handlers should be idempotent. Documented in the queue guide.
- Deferred parity-additive items: in-flight vs available metrics for `queue:size`;
  per-job `retry_after` override.
