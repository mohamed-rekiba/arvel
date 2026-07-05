"""arvel.database.connections — async engine resolution over SQLAlchemy.

``ConnectionResolver`` creates/caches async engines per named connection (default
in-memory SQLite) and runs SQLAlchemy **Core** statements: ``fetch_all``/
``fetch_one`` (reads) and ``execute`` (writes/DDL, in a transaction) returning a
small ``WriteResult`` (rowcount + inserted PK). It also offers an optional **query
log** and dispatches a ``QueryExecuted`` event (via the EventDispatcher contract —
this module never imports ``arvel.events``). SQLAlchemy is **lazy-imported** here so
``import arvel`` stays light. Grounded in knowledge/port/07 + 08.
"""

from __future__ import annotations

import contextlib
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping

    from arvel.database.builder import Builder

_DEFAULT_CONFIG: dict[str, dict[str, Any]] = {"default": {"url": "sqlite+aiosqlite://"}}

# SQLSTATE class 40 = transaction rollback: 40001 serialization_failure, 40P01 deadlock_detected.
# MySQL surfaces these as vendor codes 1213 (deadlock) / 1205 (lock wait timeout) with no SQLSTATE.
_TRANSIENT_SQLSTATES = frozenset({"40001", "40P01"})
_TRANSIENT_MYSQL_CODES = frozenset({1213, 1205})


def _is_transient(exc: Any) -> bool:
    """Whether a DBAPI error is a retryable deadlock/serialization failure (vs a permanent
    constraint/programming error). Reads the driver's own SQLSTATE / vendor code, not the
    SQLAlchemy wrapper type — those subclass a common base and can't be told apart by class."""
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate in _TRANSIENT_SQLSTATES:
        return True
    args: Any = getattr(orig, "args", None)
    return bool(args) and args[0] in _TRANSIENT_MYSQL_CODES

# the innermost open transaction's connection, so nested transaction() calls become SAVEPOINTs
_active_conn: ContextVar[Any] = ContextVar("arvel_db_active_conn", default=None)

# Connections that have had a write this async context — sticky reads route to the writer.
_sticky: ContextVar[frozenset[str]] = ContextVar("arvel_db_sticky", default=frozenset())


@dataclass
class WriteResult:
    rowcount: int
    primary_key: Any = None


@dataclass
class QueryExecuted:
    """Event emitted after a statement runs (query log / telemetry, doc 08)."""

    sql: str
    time_ms: float
    connection: str = "default"


class ConnectionResolver:
    """Resolves + caches async SQLAlchemy engines and runs Core statements."""

    def __init__(self, config: Mapping[str, Any] | None = None, default: str = "default") -> None:
        self._config: dict[str, Any] = dict(config) if config else dict(_DEFAULT_CONFIG)
        self._default = default
        self._engines: dict[str, Any] = {}
        self._query_log: list[dict[str, Any]] | None = None

    def _create(self, url: str) -> Any:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import StaticPool

        kwargs: dict[str, Any] = {}
        # In-memory SQLite needs a single shared connection to persist across calls.
        if url.replace("sqlite+aiosqlite://", "") in ("", ":memory:"):
            kwargs = {"poolclass": StaticPool}
        return create_async_engine(url, **kwargs)

    def _engine_for(self, cache_key: str, url: str) -> Any:
        if cache_key not in self._engines:
            self._engines[cache_key] = self._create(url)
        return self._engines[cache_key]

    def engine(self, name: str | None = None, mode: str = "write") -> Any:
        """The async engine for ``name``. With a ``read``/``write`` split config, ``mode``
        selects the reader or writer (a sticky connection routes reads to the writer once
        it has been written to this context). A flat config shares one engine for both."""
        key = name or self._default
        config = self._config[key]
        if "read" not in config and "write" not in config:  # flat — one engine
            return self._engine_for(key, str(config["url"]))
        actual = mode
        if mode == "read" and config.get("sticky") and key in _sticky.get():
            actual = "write"
        sub = config.get(actual) or config.get("write") or config.get("read")
        return self._engine_for(f"{key}:{actual}", str(sub["url"]))

    def dialect(self, name: str | None = None) -> str:
        """The active connection's SQL dialect name — ``"postgresql"``, ``"sqlite"``, ``"mysql"``,
        ``"mariadb"`` — for dialect-specific branches without reaching into the engine."""
        return str(self.engine(name).dialect.name)

    def table(self, name: str, connection: str | None = None) -> Builder:
        """A query builder over a raw table or view by ``name`` — arvel's ``DB::table()``. Unlike a
        model query it does **not** hydrate: ``get()`` yields plain ``dict`` rows. Use it for views,
        aggregates, and reporting reads that have no model. Columns resolve as raw identifiers, so
        bare and ``"table.column"`` names both work."""
        import sqlalchemy as sa

        from arvel.database.builder import Builder

        return Builder(sa.table(name), self)

    async def refresh_materialized_view(
        self, name: str, *, concurrently: bool = False, connection: str | None = None
    ) -> None:
        """Refresh a Postgres materialized view (created via ``Schema.create_materialized_view``).

        With ``concurrently=True`` readers are not blocked, but the view needs a unique index and the
        refresh runs outside a transaction (so this uses an ``AUTOCOMMIT`` connection, not the
        transactional :meth:`statement`). A no-op on dialects without materialized views — sqlite/
        mysql degrade them to live plain views, which have nothing to refresh."""
        import sqlalchemy as sa

        engine = self.engine(connection)
        if engine.dialect.name != "postgresql":
            return
        quoted = engine.dialect.identifier_preparer.quote(name)  # injection-safe DDL identifier
        clause = "CONCURRENTLY " if concurrently else ""
        async with engine.connect() as conn:
            autocommit = await conn.execution_options(isolation_level="AUTOCOMMIT")
            await autocommit.execute(sa.text(f"REFRESH MATERIALIZED VIEW {clause}{quoted}"))

    def _mark_sticky(self, name: str | None) -> None:
        key = name or self._default
        config = self._config[key]
        if ("read" in config or "write" in config) and config.get("sticky"):
            _sticky.set(_sticky.get() | {key})

    # --- query log ----------------------------------------------------------
    def enable_query_log(self) -> None:
        self._query_log = []

    def disable_query_log(self) -> None:
        self._query_log = None

    def flush_query_log(self) -> None:
        if self._query_log is not None:
            self._query_log = []

    def get_query_log(self) -> list[dict[str, Any]]:
        return list(self._query_log or [])

    async def _record(self, statement: Any, elapsed_ms: float, name: str | None) -> None:
        sql = str(statement)
        rounded = round(elapsed_ms, 3)
        if self._query_log is not None:
            self._query_log.append({"sql": sql, "time_ms": rounded})
        from arvel.kernel import app, has_application

        if has_application() and app().bound("events"):
            await app().make("events").dispatch(QueryExecuted(sql, rounded, name or self._default))

    # --- telemetry ----------------------------------------------------------
    def _dialect(self, name: str | None) -> str:
        """Dialect name for ``db.system`` (best-effort: sqlite/postgresql/mysql)."""
        try:
            return str(self.engine(name).dialect.name)
        except Exception:
            return "sql"

    @contextlib.contextmanager
    def _trace_query(self, statement: Any, name: str | None) -> Any:
        """Wrap a query in a CLIENT span when tracing is on, via ``arvel.telemetry.span()`` — the
        same gated helper every other module (cache, the HTTP client, …) instruments through, not
        OpenTelemetry's own API directly (that helper already sets ERROR status + records the
        exception on a raise, then re-raises unchanged). A no-op (no opentelemetry import, and —
        the early return below — no SQL-compiling ``str(statement)`` either) when tracing is off.
        ``db.statement`` is the unbound SQL — placeholders only, never bind values (DR-0020)."""
        from arvel.telemetry import is_tracing_enabled
        from arvel.telemetry import span as _span

        if not is_tracing_enabled():
            yield
            return
        sql = str(statement)
        operation = sql.split(None, 1)[0].upper() if sql.strip() else "QUERY"
        with _span(
            f"db {operation}",
            kind="client",
            attributes={"db.system": self._dialect(name), "db.statement": sql},
        ):
            yield

    # --- reads / writes -----------------------------------------------------
    async def fetch_all(self, statement: Any, name: str | None = None) -> list[Any]:
        start = time.perf_counter()
        with self._trace_query(statement, name):
            active = _active_conn.get()
            if active is not None:  # inside a transaction → run on its connection
                rows = list((await active.execute(statement)).mappings().all())
            else:
                async with self.engine(name, "read").connect() as conn:
                    rows = list((await conn.execute(statement)).mappings().all())
        await self._record(statement, (time.perf_counter() - start) * 1000, name)
        return rows

    async def fetch_one(self, statement: Any, name: str | None = None) -> Any:
        rows = await self.fetch_all(statement, name)
        return rows[0] if rows else None

    async def scalar(self, statement: Any, name: str | None = None) -> Any:
        start = time.perf_counter()
        with self._trace_query(statement, name):
            active = _active_conn.get()
            if active is not None:
                value = (await active.execute(statement)).scalar()
            else:
                async with self.engine(name, "read").connect() as conn:
                    value = (await conn.execute(statement)).scalar()
        await self._record(statement, (time.perf_counter() - start) * 1000, name)
        return value

    @staticmethod
    def call_function_statement(name: str, *args: Any, **kwargs: Any) -> Any:
        """A Core ``SELECT func.<name>(...)`` — the function name goes through SQLAlchemy's
        ``func`` registry (never f-string-interpolated), so it's injection-safe (D7)."""
        import sqlalchemy as sa

        params = [*args, *kwargs.values()]  # SQL function args are positional; kwargs keep order
        return sa.select(getattr(sa.func, name)(*params))

    async def call_function(
        self, name: str, *args: Any, connection: str | None = None, **kwargs: Any
    ) -> Any:
        """Invoke a stored DB function and return its scalar result (doc 08 §59)."""
        return await self.scalar(self.call_function_statement(name, *args, **kwargs), connection)

    @staticmethod
    def _write_meta(result: Any) -> tuple[Any, int]:
        primary_key = None
        if getattr(result, "is_insert", False):
            inserted = result.inserted_primary_key
            primary_key = inserted[0] if inserted else None
        return primary_key, getattr(result, "rowcount", -1)

    async def execute(self, statement: Any, name: str | None = None) -> WriteResult:
        start = time.perf_counter()
        with self._trace_query(statement, name):
            active = _active_conn.get()
            if active is not None:  # inside a transaction → write on its connection (no commit)
                primary_key, rowcount = self._write_meta(await active.execute(statement))
            else:
                async with self.engine(name, "write").begin() as conn:
                    primary_key, rowcount = self._write_meta(await conn.execute(statement))
        self._mark_sticky(name)
        await self._record(statement, (time.perf_counter() - start) * 1000, name)
        return WriteResult(rowcount=rowcount, primary_key=primary_key)

    @contextlib.asynccontextmanager
    async def begin_test_transaction(self, name: str | None = None) -> AsyncGenerator[Any]:
        """Open a transaction, make it the active connection, and **always roll back** on exit.

        Wraps a test so its writes are isolated — every query inside runs on this connection
        and is undone afterward, leaving the database untouched between tests.
        """
        async with self.engine(name).connect() as conn:
            txn = await conn.begin()
            token = _active_conn.set(conn)
            try:
                yield conn
            finally:
                _active_conn.reset(token)
                await txn.rollback()

    # --- transactions -------------------------------------------------------
    @contextlib.asynccontextmanager
    async def transaction(self, name: str | None = None) -> AsyncGenerator[Any]:
        """Atomic block; nesting inside an open transaction opens a SAVEPOINT."""
        existing = _active_conn.get()
        if existing is not None:
            async with existing.begin_nested():  # savepoint — inner rollback ≠ outer
                yield existing
            return
        async with self.engine(name).begin() as conn:
            token = _active_conn.set(conn)
            try:
                yield conn
            finally:
                _active_conn.reset(token)

    def transactional(self, fn: Any) -> Any:
        """Decorator form of :meth:`transaction` — wrap an async function so each call runs in a
        transaction (commit on return, rollback on raise). Nesting opens a SAVEPOINT, same as the
        context-manager form: ``@db.transactional`` over ``async with db.transaction()``."""
        import functools

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            async with self.transaction():
                return await fn(*args, **kwargs)

        return wrapper

    async def transact(self, callback: Any, name: str | None = None, *, attempts: int = 1) -> Any:
        """Run ``callback(conn)`` in a transaction; retry only on a *transient* failure
        (deadlock / serialization failure) up to ``attempts`` times. A permanent error
        (constraint violation, bad SQL) raises immediately without burning retries (doc 08)."""
        from sqlalchemy.exc import DBAPIError

        last: Exception | None = None
        for _ in range(max(1, attempts)):
            try:
                async with self.transaction(name) as conn:
                    return await callback(conn)
            except DBAPIError as exc:
                if not _is_transient(exc):
                    raise  # permanent (integrity/programming/data) — don't retry
                last = exc
        raise last if last is not None else RuntimeError("transaction failed")

    async def select(self, sql: str, params: Any = None, name: str | None = None) -> list[Any]:
        """Run a raw SQL SELECT (parameterized) and return mapped rows."""
        import sqlalchemy as sa

        statement = sa.text(sql)
        async with self.engine(name).connect() as conn:
            start = time.perf_counter()
            result = await conn.execute(statement, params or {})
            rows = list(result.mappings().all())
        await self._record(statement, (time.perf_counter() - start) * 1000, name)
        return rows

    async def statement(self, sql: str, params: Any = None, name: str | None = None) -> Any:
        """Run a raw SQL statement (INSERT/UPDATE/DDL) in a transaction."""
        import sqlalchemy as sa

        async with self.engine(name).begin() as conn:
            return await conn.execute(sa.text(sql), params or {})

    async def stream(self, statement: Any, name: str | None = None) -> AsyncGenerator[Any]:
        """Stream mapped rows one at a time (server-side cursor) for low-memory reads."""
        async with self.engine(name).connect() as conn:
            result = await conn.stream(statement)
            async for row in result.mappings():
                yield dict(row)

    async def dispose(self) -> None:
        for engine in self._engines.values():
            await engine.dispose()
        self._engines.clear()
