# ADR-037: Debugging and query-log parity

Status: Accepted (delivered WI-arvel-013)

Eloquent-parity increment (backlog `005`, story S11). No HTTP or schema surface —
recorded as an ADR.

## ADR-037-01: Query logging hooks the engine, not the QueryBuilder

Status: Accepted

There's already a test helper (`QueryLog.capture()`) that listens on the bound engine for a
with-block. For a Laravel-style `DB::enableQueryLog()` we need the same coverage at the
facade level, capturing `{sql, bindings, time_ms}` for **all** traffic — query builder, raw
`DB.select`, relationship loads — not just statements that route through one method.

So `DB.enable_query_log()` installs `before_cursor_execute` / `after_cursor_execute`
listeners on `engine.sync_engine`. Every executed cursor is recorded regardless of which
Python API produced it. Timing uses a per-connection stack in `conn.info` (the SQLAlchemy-
recommended pattern) so nested/concurrent executions pair their start and end correctly.

The removers are kept in a **list** ClassVar rather than a bare `Callable` attribute —
storing a function directly on the class reads as a method definition to the type checker.

## ADR-037-02: `pretend` rolls back rather than truly skipping execution

Status: Accepted

Laravel's `pretend` flips a connection flag so writes are logged but never sent. Our async
SQLAlchemy stack has no single execution chokepoint to intercept, and faking result objects
for skipped SELECTs would be fragile.

`DB.pretend(callback)` instead opens a transaction, captures the SQL into a local sink, runs
the callback, and **rolls back** — statements execute against the connection but nothing
persists. It returns the captured log. The semantic difference (executed-then-discarded vs
never-executed) is documented; for previewing writes without committing them, the behavior
is equivalent and safe.

## ADR-037-03: `to_raw_sql` / `get_bindings` / `explain` on the builder

Status: Accepted

- `to_raw_sql()` returns SQL with bindings inlined — it reuses `to_sql()` (already compiles
  with `literal_binds=True`). Kept as a named method to match Laravel's `toRawSql`.
- `get_bindings()` returns the compiled statement's parameter values in order
  (`compiled.params.values()`), like Laravel's `getBindings`.
- `explain()` runs the dialect's plan command — `EXPLAIN QUERY PLAN` on SQLite, `EXPLAIN`
  elsewhere — against the inlined SQL and returns the plan rows as dicts.
