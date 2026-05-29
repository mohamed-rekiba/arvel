"""DB facade — transaction management, raw SQL, and table query builder."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from typing import Any, ClassVar, cast

from sqlalchemy import ColumnClause, Select, text
from sqlalchemy import delete as sqla_delete
from sqlalchemy import insert as sqla_insert
from sqlalchemy import select as sqla_select
from sqlalchemy import update as sqla_update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.sql import TableClause
from sqlalchemy.sql import column as sqla_column
from sqlalchemy.sql import table as sqla_table

from arvel.database.session import (
    enqueue_after_commit,
    get_after_commit_queue,
    get_optional_session,
    reset_active_session,
    reset_after_commit_queue,
    set_active_session,
    set_after_commit_queue,
)


class TableQueryBuilder:
    """Model-free query builder that returns raw dicts instead of ORM instances.

    Returned by ``DB.table("table_name")``. All statements are built with
    SQLAlchemy Core (``select/insert/update/delete`` on a lightweight
    ``TableClause``) so identifiers are quoted and values are bound by the
    driver — no string-concatenation injection vectors.
    """

    def __init__(
        self,
        table_name: str,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._table_name = table_name
        self._session_maker = session_maker
        self._where_clauses: list[tuple[str, Any]] = []
        self._limit_val: int | None = None
        self._order_col: str | None = None

    def _session(self) -> AsyncSession:
        existing = get_optional_session()
        if existing is not None:
            return existing
        if self._session_maker is not None:
            raise RuntimeError(
                "TableQueryBuilder.get/insert/update requires an active DB session. "
                "Use inside a DB.transaction() context or an HTTP request."
            )
        raise RuntimeError("No active session for TableQueryBuilder.")

    def _table_clause(self, *extra_columns: str) -> TableClause:
        col_names = {c for c, _ in self._where_clauses}
        col_names.update(extra_columns)
        if self._order_col:
            col_names.add(self._order_col)
        cols: list[ColumnClause[Any]] = [sqla_column(c) for c in col_names]
        return sqla_table(self._table_name, *cols)

    def where(self, col: str, value: Any) -> TableQueryBuilder:
        new = TableQueryBuilder(self._table_name, self._session_maker)
        new._where_clauses = [*self._where_clauses, (col, value)]
        new._limit_val = self._limit_val
        new._order_col = self._order_col
        return new

    def limit(self, n: int) -> TableQueryBuilder:
        new = TableQueryBuilder(self._table_name, self._session_maker)
        new._where_clauses = list(self._where_clauses)
        new._limit_val = n
        new._order_col = self._order_col
        return new

    def order_by(self, col: str) -> TableQueryBuilder:
        new = TableQueryBuilder(self._table_name, self._session_maker)
        new._where_clauses = list(self._where_clauses)
        new._limit_val = self._limit_val
        new._order_col = col
        return new

    def _apply_where(self, stmt: Any, tbl: Any) -> Any:
        for col, value in self._where_clauses:
            stmt = stmt.where(tbl.c[col] == value)
        return stmt

    async def get(self) -> list[dict[str, Any]]:
        from sqlalchemy import literal_column

        tbl = self._table_clause()
        star: ColumnClause[Any] = literal_column("*")
        stmt: Select[Any] = sqla_select(star).select_from(tbl)
        stmt = self._apply_where(stmt, tbl)
        if self._order_col:
            stmt = stmt.order_by(tbl.c[self._order_col])
        if self._limit_val is not None:
            stmt = stmt.limit(self._limit_val)
        session = self._session()
        result = await session.execute(stmt)
        return [dict(row) for row in result.mappings().all()]

    async def insert(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        cols: list[ColumnClause[Any]] = [sqla_column(c) for c in rows[0]]
        tbl = sqla_table(self._table_name, *cols)
        session = self._session()
        await session.execute(sqla_insert(tbl), rows)
        await session.flush()

    async def update(self, values: dict[str, Any]) -> int:
        tbl = self._table_clause(*values.keys())
        stmt = sqla_update(tbl).values(**values)
        stmt = self._apply_where(stmt, tbl)
        session = self._session()
        result = cast("CursorResult[Any]", await session.execute(stmt))
        await session.flush()
        return result.rowcount

    async def delete(self) -> int:
        tbl = self._table_clause()
        stmt = sqla_delete(tbl)
        stmt = self._apply_where(stmt, tbl)
        session = self._session()
        result = cast("CursorResult[Any]", await session.execute(stmt))
        await session.flush()
        return result.rowcount


class _DBProxy:
    """Proxy for a named DB connection that exposes the same raw SQL helpers as DB."""

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        self._session_maker = session_maker

    async def select(
        self, sql: str, bindings: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        async with self._session_maker() as session:
            result = await session.execute(text(sql).bindparams(**(bindings or {})))
            return [dict(row) for row in result.mappings().all()]

    async def scalar(self, sql: str, bindings: dict[str, Any] | None = None) -> Any:
        async with self._session_maker() as session:
            result = await session.execute(text(sql).bindparams(**(bindings or {})))
            return result.scalar()

    async def statement(self, sql: str, bindings: dict[str, Any] | None = None) -> None:
        async with self._session_maker() as session:
            await session.execute(text(sql).bindparams(**(bindings or {})))
            await session.flush()

    def table(self, table_name: str) -> TableQueryBuilder:
        return TableQueryBuilder(table_name, self._session_maker)


class DB:
    """Facade for explicit transaction management and raw SQL execution.

    Typical usage::

        async with DB.transaction():
            await user.save()
            await order.save()

    Nested calls create savepoints::

        async with DB.transaction():
            await payment.save()
            async with DB.transaction():   # → SAVEPOINT
                await ledger.save()

    For DDL-like operations that cannot run inside a transaction (e.g.
    ``REFRESH MATERIALIZED VIEW CONCURRENTLY``), use :meth:`autocommit`::

        async with DB.autocommit() as conn:
            await conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY my_view"))
    """

    _session_maker: ClassVar[async_sessionmaker[AsyncSession] | None] = None
    _engine: ClassVar[AsyncEngine | None] = None
    _named_makers: ClassVar[dict[str, async_sessionmaker[AsyncSession]]] = {}
    _listeners: ClassVar[list[Any]] = []

    @classmethod
    def configure(cls, session_maker: async_sessionmaker[AsyncSession]) -> None:
        cls._session_maker = session_maker

    @classmethod
    def configure_engine(cls, engine: AsyncEngine) -> None:
        """Store the raw engine for use cases that need a bare connection (e.g. autocommit)."""
        cls._engine = engine

    @classmethod
    @asynccontextmanager
    async def autocommit(cls) -> AsyncGenerator[AsyncConnection]:
        """Yield a raw connection with ``AUTOCOMMIT`` isolation.

        Use this for statements that cannot run inside a transaction block, such
        as ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` or ``CREATE INDEX
        CONCURRENTLY``.  The caller's active session (if any) is left untouched —
        this connection is completely independent.
        """
        if cls._engine is None:
            raise RuntimeError(
                "DB.autocommit() called before DB.configure_engine(). "
                "Register DatabaseServiceProvider or call DB.configure_engine(engine) first."
            )
        async with cls._engine.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            yield conn

    @classmethod
    def configure_named(cls, name: str, session_maker: async_sessionmaker[AsyncSession]) -> None:
        cls._named_makers[name] = session_maker

    @classmethod
    def connection(cls, name: str | None = None) -> _DBProxy:
        if name is None:
            if cls._session_maker is None:
                raise RuntimeError("DB not configured. Call DB.configure() first.")
            return _DBProxy(cls._session_maker)
        maker = cls._named_makers.get(name)
        if maker is None:
            raise RuntimeError(
                f"No named connection '{name}' registered with DB.configure_named()."
            )
        return _DBProxy(maker)

    @classmethod
    def table(cls, table_name: str) -> TableQueryBuilder:
        return TableQueryBuilder(table_name)

    @classmethod
    async def select(cls, sql: str, bindings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a raw SELECT and return list of dicts."""
        session = get_optional_session()
        if session is None and cls._session_maker is not None:
            async with cls._session_maker() as s:
                result = await s.execute(text(sql).bindparams(**(bindings or {})))
                rows = result.mappings().all()
                cls._fire_listeners(sql, bindings or {})
                return [dict(row) for row in rows]
        if session is None:
            raise RuntimeError(
                "DB.select() requires an active session or configured session maker."
            )
        result = await session.execute(text(sql).bindparams(**(bindings or {})))
        cls._fire_listeners(sql, bindings or {})
        return [dict(row) for row in result.mappings().all()]

    @classmethod
    async def scalar(cls, sql: str, bindings: dict[str, Any] | None = None) -> Any:
        """Execute a raw SQL statement and return the first column of the first row."""
        session = get_optional_session()
        if session is None and cls._session_maker is not None:
            async with cls._session_maker() as s:
                result = await s.execute(text(sql).bindparams(**(bindings or {})))
                cls._fire_listeners(sql, bindings or {})
                return result.scalar()
        if session is None:
            raise RuntimeError(
                "DB.scalar() requires an active session or configured session maker."
            )
        result = await session.execute(text(sql).bindparams(**(bindings or {})))
        cls._fire_listeners(sql, bindings or {})
        return result.scalar()

    @classmethod
    async def statement(cls, sql: str, bindings: dict[str, Any] | None = None) -> None:
        """Execute a raw SQL statement with no return value."""
        session = get_optional_session()
        if session is None and cls._session_maker is not None:
            async with cls._session_maker() as s:
                await s.execute(text(sql).bindparams(**(bindings or {})))
                await s.flush()
                cls._fire_listeners(sql, bindings or {})
                return
        if session is None:
            raise RuntimeError(
                "DB.statement() requires an active session or configured session maker."
            )
        await session.execute(text(sql).bindparams(**(bindings or {})))
        await session.flush()
        cls._fire_listeners(sql, bindings or {})

    @classmethod
    def listen(cls, handler: Any) -> None:
        """Register a callable invoked after each raw SQL execution.

        Signature: ``handler(sql: str, bindings: dict, duration_ms: float) -> None``
        """
        if handler not in cls._listeners:
            cls._listeners.append(handler)

    @classmethod
    def unlisten(cls, handler: Any) -> None:
        if handler in cls._listeners:
            cls._listeners.remove(handler)

    @classmethod
    def _fire_listeners(cls, sql: str, bindings: dict[str, Any]) -> None:
        for handler in cls._listeners:
            with suppress(Exception):
                handler(sql, bindings, 0.0)

    @classmethod
    def after_commit(cls, fn: Callable[[], Awaitable[Any]]) -> None:
        """Register ``fn`` to be awaited once the surrounding transaction commits.

        Must be called inside a ``DB.transaction()`` block or an HTTP request
        wrapped by ``DatabaseTransaction`` middleware.  Raises ``RuntimeError``
        if no transaction context is active.

        Callbacks registered inside a nested ``DB.transaction()`` (savepoint)
        are deferred to the outermost commit — the one that actually writes to
        disk.

        Callbacks are **not** called if the transaction rolls back.
        """
        enqueue_after_commit(fn)

    @classmethod
    @asynccontextmanager
    async def transaction(cls) -> AsyncGenerator[AsyncSession]:
        existing = get_optional_session()
        if existing is not None:
            # Nested path — savepoint.  Any DB.after_commit() calls inside here
            # enqueue on the outer queue (set by the middleware or outermost
            # DB.transaction()), so they fire when the real COMMIT happens.
            async with existing.begin_nested():
                yield existing
            return

        if cls._session_maker is None:
            raise RuntimeError(
                "DB.transaction() called before DB.configure(). "
                "Register DatabaseServiceProvider or call DB.configure(session_maker) "
                "in your bootstrap."
            )

        # Outermost transaction — own the callback queue if no outer context has
        # one already (e.g. called outside of an HTTP request).
        is_queue_owner = get_after_commit_queue() is None
        callbacks: list[Callable[[], Awaitable[Any]]] = []
        q_token = set_after_commit_queue(callbacks) if is_queue_owner else None

        committed = False
        try:
            async with cls._session_maker() as session:
                s_token = set_active_session(session)
                try:
                    async with session.begin():
                        yield session
                    committed = True
                finally:
                    reset_active_session(s_token)
        finally:
            if q_token is not None:
                reset_after_commit_queue(q_token)

        if committed and is_queue_owner:
            for cb in callbacks:
                await cb()


__all__ = ["DB", "TableQueryBuilder"]
