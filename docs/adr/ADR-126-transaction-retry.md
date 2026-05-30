# ADR-126: Closure-form Transaction Retry on Deadlock

Status: Accepted

Eloquent-parity increment (backlog `005`, Sprint B: story S12, partial). No HTTP or
schema surface — recorded as an ADR.

## ADR-126-01: Retry needs a closure form, separate from the CM `transaction()`

Status: Accepted

`DB.transaction()` is an `@asynccontextmanager` — the caller's `async with` body runs
exactly once, so a context manager can't re-run the body after a deadlock. Retry
requires the work to be a **callable** the facade can invoke again.

Rather than overload `transaction()` to return either a context manager or a coroutine
(which can't be typed cleanly under pyright strict), we add a distinct generic method:

```python
await DB.transactional(callback, attempts=3)   # callback: (AsyncSession) -> Awaitable[T]
```

Each attempt opens a fresh outermost `transaction()` (new session, real COMMIT/ROLLBACK),
so a rolled-back attempt leaves no state behind before the next try. The CM form is
unchanged for the common single-attempt case.

## ADR-126-02: Retry only on deadlock / serialization failures

Status: Accepted

`_is_retryable_db_error` returns true only for SQLAlchemy `OperationalError` /
`DBAPIError` whose driver error signals a deadlock or serialization conflict —
PostgreSQL SQLSTATE `40001` (serialization_failure) / `40P01` (deadlock_detected), or a
message token (`deadlock`, `serialization`, `could not serialize`, `database is locked`,
`lock wait timeout`). Everything else (integrity violations, app errors) propagates
immediately — retrying a logic error would just burn attempts and hide the bug.

## ADR-126-03: Imperative begin/commit/rollback deferred

Status: Accepted

Story S12 also lists imperative `begin_transaction`/`commit`/`rollback` with savepoint
interop. That's a separate concern with real lifecycle risk under the ContextVar-based
session model (manual token management, nesting). It's deliberately **out of scope**
here — the retry is the high-value, low-risk, shared-infra core (used by the `*_quietly`
writes). S12 stays open for the imperative-control follow-up.
