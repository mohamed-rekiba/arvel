# ADR-040: Closure-form Transaction Retry on Deadlock

Status: Accepted

Eloquent-parity increment (backlog `005`, Sprint B: story S12, partial). No HTTP or
schema surface — recorded as an ADR.

## ADR-040-01: Retry needs a closure form, separate from the CM `transaction()`

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

## ADR-040-02: Retry only on deadlock / serialization failures

Status: Accepted

`_is_retryable_db_error` returns true only for SQLAlchemy `OperationalError` /
`DBAPIError` whose driver error signals a deadlock or serialization conflict —
PostgreSQL SQLSTATE `40001` (serialization_failure) / `40P01` (deadlock_detected), or a
message token (`deadlock`, `serialization`, `could not serialize`, `database is locked`,
`lock wait timeout`). Everything else (integrity violations, app errors) propagates
immediately — retrying a logic error would just burn attempts and hide the bug.

## ADR-040-03: Imperative begin/commit/rollback via a frame stack

Status: Accepted (delivered WI-arvel-010)

Story S12 also lists imperative `begin_transaction`/`commit`/`rollback` with savepoint
interop. The earlier increment deferred it for lifecycle risk under the ContextVar session
model; this increment delivers it with an explicit frame stack instead of ad-hoc token
juggling.

`DB.begin_transaction()` pushes a `_TxnFrame` onto a context-local stack (`_IMPERATIVE_TXN`):

- **Outermost** (no active session): open a fresh session, `await session.begin()`, install
  it as the active session, and — if no outer after-commit queue exists — own a new one. The
  frame records the session/queue reset tokens.
- **Nested** (a session is already active, whether from a prior `begin_transaction()` or a
  surrounding `DB.transaction()` block): `await session.begin_nested()` opens a SAVEPOINT.
  The frame owns nothing.

`commit()` / `rollback()` pop the top frame. A savepoint frame commits (release) or rolls
back to the savepoint and returns. An outermost frame commits/rolls back the session, resets
the queue and session tokens it owns, closes the session, and — on commit only — fires the
after-commit callbacks. Calling `commit`/`rollback` with an empty stack raises.

Because nesting is decided by "is a session already active?", imperative savepoints compose
with the context-manager `transaction()` for free: a `begin_transaction()` inside an
`async with DB.transaction():` block is a savepoint on the context-managed session.
