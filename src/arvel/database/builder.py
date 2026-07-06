"""arvel.database.builder — the query builder on SQLAlchemy Core.

The G4-load-bearing piece: ``Builder`` composes **SQLAlchemy Core construct
objects** (``select()``/``insert()``/``update()``/``delete()`` + ``and_()``/``or_()``
over ``Table``/``Column`` metadata) — never raw SQL strings — so the *same* builder
call compiles correctly to every dialect. SQLAlchemy is lazy-imported. *Lazy-import ≠
reimplement* (doc 00 §5b). Grounded in knowledge/port/07-orm-active-record.md.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Self, cast

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Sequence

    from sqlalchemy import Select

    from arvel.database.connections import ConnectionResolver, WriteResult
    from arvel.pagination import CursorPaginator, LengthAwarePaginator, Paginator


class UnsupportedDriverOperation(Exception):
    """Raised when an operation has no correct implementation for the connection's dialect —
    e.g. ``upsert()`` on a dialect that's neither ``postgresql``/``sqlite`` (``ON CONFLICT``) nor
    ``mysql``/``mariadb`` (``ON DUPLICATE KEY UPDATE``). Never silently emit the wrong SQL (A4)."""


async def _maybe_await(value: Any) -> Any:
    """Await ``value`` if it's awaitable, else pass it through — ``hydrate`` accepts either a
    sync callable (``Model._hydrate``, a stable direct-call surface) or an async one
    (``Model._hydrate_and_fire``, used by the model's own query path to fire ``retrieved``)."""
    import inspect

    return await value if inspect.isawaitable(value) else value


_COMPARISONS = {
    "=": "__eq__",
    "==": "__eq__",
    "!=": "__ne__",
    ">": "__gt__",
    ">=": "__ge__",
    "<": "__lt__",
    "<=": "__le__",
}

# A strict SQL identifier — bare ``column`` or ``table.column``, letters/digits/underscore only.
# Guards the schema-less ``DB.table`` builder's column names (no Table.c to validate against) so an
# injection payload like ``"id; DROP TABLE users--"`` can never become a literal column.
_SAFE_COLUMN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


class Builder:
    """Fluent query builder emitting SQLAlchemy Core statements."""

    def __init__(
        self,
        table: Any,
        resolver: ConnectionResolver | None = None,
        hydrate: Callable[[dict[str, Any]], Any] | None = None,
        model: Any = None,
    ) -> None:
        self._table = table
        self._resolver = resolver
        self._hydrate = hydrate
        self._model = model  # the Model class, for resolving relations in where_has/with_count
        self._wheres: list[tuple[str, Any]] = []  # (connector, clause)
        self._order: list[Any] = []
        self._order_specs: list[
            tuple[str, str]
        ] = []  # (column, direction) — powers cursor_paginate
        self._columns: list[str] | None = None
        self._raw_selects: list[Any] = []  # select_raw() expressions (spec 08 §42)
        self._group_by: list[str] = []  # group_by() column / alias names
        self._havings: list[tuple[str, Any]] = []  # (connector, clause) — HAVING, post-group_by
        self._joins: list[tuple[str, str, str, str, str]] = []  # (table, first, op, second, kind)
        self._distinct = False
        self._limit: int | None = None
        self._offset: int | None = None
        self._eager: list[str] = []
        self._eager_constraints: dict[str, Any] = {}  # per-relation constrained eager load (D2)
        self._lock: str | None = None
        self._aggregates: list[Any] = []  # labeled scalar subqueries (with_count/with_sum)

    def __getattr__(self, name: str) -> Any:
        # local scopes: a model method `scope_<name>` becomes callable as `.<name>(...)`
        if name.startswith("_"):
            raise AttributeError(name)
        model = self.__dict__.get("_model")
        if model is None:
            raise AttributeError(name)
        instance = model()
        scope = getattr(instance, f"scope_{name}", None)
        if scope is None:
            # ...or a method marked with @scope (no scope_ prefix; stripped from the class).
            model_cls = cast("Any", type(instance))
            local_scopes = cast("dict[str, Any]", getattr(model_cls, "__local_scopes__", {}))
            func = local_scopes.get(name)
            if func is not None:
                scope = func.__get__(instance)  # bind to the model instance
        if scope is None:
            raise AttributeError(name)

        def apply(*args: Any, **kwargs: Any) -> Builder:
            result = scope(self, *args, **kwargs)
            return result if isinstance(result, Builder) else self

        return apply

    def with_(self, *names: str, **constrained: Any) -> Self:
        """Eager-load the named relations (batched WHERE IN; no N+1).

        Pass a relation as a **keyword** with a callback to *constrain* its query, so only the
        matching rows are fetched in the same batch — e.g. load just one media collection::

            await Post.with_(media=lambda q: q.where(collection_name="images")).get()
        """
        self._eager.extend(names)
        for name, constraint in constrained.items():
            self._eager.append(name)
            self._eager_constraints[name] = constraint
        return self

    # --- where -------------------------------------------------------------
    def _add(self, clause: Any, connector: str = "and") -> None:
        self._wheres.append((connector, clause))

    @staticmethod
    def _bind(value: Any) -> Any:
        """Adapt an arvel value object to what the DB driver binds: an arvel ``Date`` becomes its
        UTC-aware stdlib datetime, so ``where("col", "<", Date.now())`` works without the caller
        dropping to ``.to_py()``. Other values pass through."""
        from arvel.dates import Date

        return value.raw.to_tz("UTC").to_stdlib() if isinstance(value, Date) else value

    def _value_comparison(self, expr: Any, operator: str, value: Any) -> Any:
        """Compare an arbitrary SQL expression (a column, or a derived expression like
        ``sa.func.date(col)``/``sa.extract("year", col)``) against a bound ``value``."""
        if operator == "like":
            return expr.like(value)
        if operator == "in":
            return expr.in_([self._bind(v) for v in value])
        return getattr(expr, _COMPARISONS[operator])(self._bind(value))

    def _comparison(self, column: str, operator: str, value: Any) -> Any:
        col = self._where_column(column)
        if operator == "ilike":
            # native ILIKE on PostgreSQL; SQLAlchemy lowers both sides elsewhere
            return col.ilike(value)
        return self._value_comparison(col, operator, value)

    def _column_or_literal(self, name: str) -> Any:
        """``name`` as a real column of this query's table, or — for a ``group_by``/``select_raw``
        alias like ``"total"`` that isn't a table column — a raw SQL identifier."""
        import sqlalchemy as sa

        cols = self._table.c
        return cast("Any", cols[name] if name in cols else sa.literal_column(name))

    def _column_ref(self, name: str) -> Any:
        """A column reference for ``where_column``/joins: ``"other.col"`` (a joined table) resolves
        to a raw dotted identifier; a bare name resolves against this query's own table (or, same
        as:meth:`_column_or_literal`, a raw identifier when it isn't one of this table's columns)."""
        import sqlalchemy as sa

        if "." in name:
            return cast("Any", sa.literal_column(name))
        return self._column_or_literal(name)

    def _where_column(self, name: str) -> Any:
        """Resolve a **filter/order** column safely (SQL-injection defense).

        A schema-backed table (a model query) validates ``name`` against its declared columns —
        an unknown identifier raises ``KeyError`` rather than being injected; filter joined or
        computed columns with ``where_raw`` (the app owns those). A schema-less ``DB.table`` builder
        has no ``Table.c`` to check, so a strictly-validated bare/``table.column`` identifier becomes
        a literal; anything else is rejected."""
        import sqlalchemy as sa

        cols = self._table.c
        if len(cols):
            return cols[name]  # KeyError on unknown = rejected, never interpolated
        if _SAFE_COLUMN.match(name):
            return cast("Any", sa.literal_column(name))
        raise KeyError(name)

    def _apply_conditions(
        self, args: tuple[Any, ...], kwargs: dict[str, Any], connector: str
    ) -> None:
        for column, val in kwargs.items():
            self._add(self._where_column(column) == self._bind(val), connector)
        if len(args) == 2:
            self._add(self._where_column(args[0]) == self._bind(args[1]), connector)
        elif len(args) == 3:
            self._add(self._comparison(args[0], args[1], args[2]), connector)

    def where(self, *args: Any, **kwargs: Any) -> Self:
        self._apply_conditions(args, kwargs, "and")
        return self

    def or_where(self, *args: Any, **kwargs: Any) -> Self:
        self._apply_conditions(args, kwargs, "or")
        return self

    def where_in(self, column: str, values: Sequence[Any] | Select[Any]) -> Self:
        """``WHERE col IN (...)``. ``values`` is a list **or a subquery** ``Select`` (``whereIn('id', $subquery)``) — pass ``sa.select(other.c.id)`` to filter DB-side without
        materializing the id list in the app (e.g. ``where_in('id', select(retrievable.c.id))``)."""
        self._add(self._where_column(column).in_(values))
        return self

    def where_not_in(self, column: str, values: Sequence[Any] | Select[Any]) -> Self:
        self._add(self._where_column(column).not_in(values))
        return self

    def or_where_in(self, column: str, values: Sequence[Any]) -> Self:
        self._add(self._where_column(column).in_(values), "or")
        return self

    def where_between(self, column: str, values: Sequence[Any]) -> Self:
        low, high = values
        self._add(self._where_column(column).between(low, high))
        return self

    def where_not_between(self, column: str, values: Sequence[Any]) -> Self:
        import sqlalchemy as sa

        low, high = values
        self._add(sa.not_(self._where_column(column).between(low, high)))
        return self

    def where_raw(self, sql: str, *, connector: str = "and") -> Self:
        """A raw SQL boolean predicate — e.g. a correlated ``EXISTS(...)``.
        The SQL is **trusted**: never interpolate user input here; use bound ``where(...)`` for values."""
        import sqlalchemy as sa

        self._add(sa.text(sql), connector)
        return self

    def where_exists(self, subquery: Select[Any], *, connector: str = "and") -> Self:
        """``WHERE EXISTS (subquery)``. ``subquery`` is a ``Select`` — correlate
        it to the outer query (``where(other.c.id == self.table.c['id'])``) for a per-row check."""
        import sqlalchemy as sa

        self._add(sa.exists(subquery), connector)
        return self

    @property
    def table(self) -> Any:
        """The underlying SQLAlchemy ``Table`` — for building a correlated ``where_exists`` subquery."""
        return self._table

    def _apply_conditional(self, callback: Any, value: Any) -> None:
        """Invoke a ``when``/``unless`` callback -style. passes ``($query, $value)``;
        we pass the value as the 2nd argument when the callback accepts one, and fall back to
        ``callback(self)`` for the common close-over-the-value 1-arg form."""
        import inspect

        takes_value = False
        try:
            params = list(inspect.signature(callback).parameters.values())
            positional = [
                p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            ]
            takes_value = len(positional) >= 2 or any(p.kind == p.VAR_POSITIONAL for p in params)
        except ValueError, TypeError:  # pragma: no cover - builtins without a signature
            takes_value = False
        if takes_value:
            callback(self, value)
        else:
            callback(self)

    def when(self, condition: Any, callback: Any, default: Any = None) -> Self:
        """``when`` — apply ``callback(self, condition)`` only if ``condition`` is truthy,
        else ``default(self, condition)`` if given. Lets conditional clauses stay in the fluent chain.

        Matches the ``when($value, fn($query, $value))``: the truthy value is passed to the
        callback's 2nd argument. A 1-arg callback (``lambda q:...``, closing over the value
        directly) also works — the value is only passed when the callback accepts it.
        """
        if condition:
            self._apply_conditional(callback, condition)
        elif default is not None:
            self._apply_conditional(default, condition)
        return self

    def unless(self, condition: Any, callback: Any, default: Any = None) -> Self:
        """``unless`` — the inverse of ``when``: apply ``callback(self, condition)`` only
        when ``condition`` is **falsy**, else ``default(self, condition)`` if given. Same
        value-passing semantics as ``when`` (the value is passed to a 2-arg callback)."""
        if not condition:
            self._apply_conditional(callback, condition)
        elif default is not None:
            self._apply_conditional(default, condition)
        return self

    # --- JSON columns (Postgres jsonb / generic JSON) ----------------------
    def _json_path(self, column: str, path: str) -> Any:
        """Index into a JSON column by a ``key`` or nested ``a->b->c`` / ``a.b.c`` path,
        returning a SQLAlchemy JSON path expression (cross-dialect: ``json_extract`` on SQLite,
        ``->``/``->>`` on Postgres)."""
        expr = self._table.c[column]
        for key in path.replace("->", ".").split("."):
            expr = expr[int(key)] if key.lstrip("-").isdigit() else expr[key]
        return expr

    def where_json(self, column: str, path: str, value: Any, *, connector: str = "and") -> Self:
        """Filter on a value *inside* a JSON column — ``where('data->lang', 'en')``.
        ``path`` is a key, a nested ``a->b`` / ``a.b`` path, or an array index. Compares the
        extracted value as text, so it works across SQLite and Postgres."""
        self._add(self._json_path(column, path).as_string() == value, connector)
        return self

    def where_json_like(
        self, column: str, path: str, value: str, *, connector: str = "and"
    ) -> Self:
        """``LIKE`` against a value inside a JSON column — ``where('data->name', 'like', '%x%')``.
        Handy for searching a per-locale translatable attribute, e.g.
        ``where_json_like('name', 'en', '%phone%')``. Cross-dialect (json_extract / ``->>``)."""
        self._add(self._json_path(column, path).as_string().like(value), connector)
        return self

    def where_json_contains(self, column: str, value: Any, *, connector: str = "and") -> Self:
        """Postgres/MySQL JSON containment — ``whereJsonContains('data->tags', 'x')``:
        rows where ``column`` contains ``value`` (the ``@>`` operator). Postgres-targeted; build
        the query on a Postgres connection."""
        import json as _json

        import sqlalchemy as sa

        col = self._table.c[column]
        self._add(col.op("@>")(sa.type_coerce(_json.dumps(value), col.type)), connector)
        return self

    def where_fulltext(
        self, column: str, query: str, *, language: str = "english", connector: str = "and"
    ) -> Self:
        """Postgres full-text search — ``whereFullText``: rows whose ``column`` matches
        the natural-language ``query``. Emits ``to_tsvector(language, column) @@
        plainto_tsquery(language, query)``. Postgres-targeted (build on a Postgres connection); for
        a precomputed ``tsvector`` column, back it with a ``gin_index`` so the match stays fast."""
        import sqlalchemy as sa

        vector = sa.func.to_tsvector(language, self._table.c[column])
        self._add(vector.op("@@")(sa.func.plainto_tsquery(language, query)), connector)
        return self

    # --- relationship existence (doc 07) -----------------------------------
    def _combined_where(self) -> Any:
        """Fold this builder's accumulated conditions into one SQLAlchemy clause (or None)."""
        import sqlalchemy as sa

        clause: Any = None
        for connector, condition in self._wheres:
            if clause is None:
                clause = condition
            elif connector == "or":
                clause = sa.or_(clause, condition)
            else:
                clause = sa.and_(clause, condition)
        return clause

    def _relation(self, name: str) -> Any:
        if self._model is None:
            raise RuntimeError(f"where_has({name!r}) needs a model-bound query")
        return getattr(self._model(), name)()  # bare instance: relation keys are class-level

    def _has_subquery(self, name: str, callback: Any) -> Any:
        import sqlalchemy as sa

        relation = self._relation(name)
        related_table = relation.related.__table__
        subquery = sa.select(sa.literal(1)).where(
            related_table.c[relation.foreign_key] == self._table.c[relation.local_key]
        )
        if callback is not None:
            constrained = Builder(related_table, model=relation.related)
            callback(constrained)
            extra = constrained._combined_where()
            if extra is not None:
                subquery = subquery.where(extra)
        return sa.exists(subquery)

    def where_has(self, relation: str, callback: Any = None, *, connector: str = "and") -> Self:
        """Constrain to parents that have ≥1 matching related row (optional callback)."""
        self._add(self._has_subquery(relation, callback), connector)
        return self

    def or_where_has(self, relation: str, callback: Any = None) -> Self:
        return self.where_has(relation, callback, connector="or")

    def has(self, relation: str) -> Self:
        return self.where_has(relation, None)

    def with_where_has(self, relation: str, callback: Any = None) -> Self:
        """Filter parents by the constrained relation AND eager-load only the rows matching
        that *same* constraint. D2."""
        self.where_has(relation, callback)
        self._eager.append(relation)
        self._eager_constraints[relation] = callback
        return self

    def _correlated_aggregate(self, name: str, aggregate: Any) -> Any:
        import sqlalchemy as sa

        relation = self._relation(name)
        related_table = relation.related.__table__
        return (
            sa.select(aggregate)
            .where(related_table.c[relation.foreign_key] == self._table.c[relation.local_key])
            .scalar_subquery()
        )

    async def chunk_by_id(self, size: int, callback: Any, *, column: str | None = None) -> None:
        """Page through results in id-ordered batches of ``size``, calling ``callback`` per
        chunk (sync or async). Keyset pagination on the primary key — stable under inserts."""
        import inspect

        key = column or (self._model.__primary_key__ if self._model is not None else "id")
        base_wheres = list(self._wheres)
        last: Any = (
            None  # no lower bound on the first page — works for string/uuid PKs, not just int
        )
        while True:
            bound = [("and", self._table.c[key] > last)] if last is not None else []
            self._wheres = [*base_wheres, *bound]
            self._order = [self._table.c[key].asc()]
            self._limit = size
            rows = await self.get()
            if not rows:
                return
            outcome = callback(rows)
            if inspect.isawaitable(outcome):
                outcome = await outcome
            if outcome is False:  # parity: the callback can stop the chunk walk early
                return
            tail = rows[-1]
            last = tail._attributes[key] if hasattr(tail, "_attributes") else tail[key]
            if len(rows) < size:
                return

    async def chunk(self, size: int, callback: Any) -> None:
        """Page through results in fixed-size **offset** batches, calling ``callback`` per chunk
        (sync or async; returning ``False`` stops early. Simpler than
        ``chunk_by_id`` but not safe under concurrent writes that shift rows between pages
        (prefer ``chunk_by_id``/``cursor`` for a frequently-written table)."""
        import inspect

        page = 0
        base_limit, base_offset = self._limit, self._offset
        try:
            while True:
                self._limit = size
                self._offset = page * size
                rows = await self.get()
                if not rows:
                    return
                outcome = callback(rows)
                if inspect.isawaitable(outcome):
                    outcome = await outcome
                if outcome is False or len(rows) < size:
                    return
                page += 1
        finally:
            self._limit, self._offset = base_limit, base_offset

    async def each(self, callback: Any, chunk_size: int = 1000) -> None:
        """Process every row individually, streaming ``chunk_size`` at a time under the hood. ``callback`` returning ``False`` stops the whole walk early."""
        import inspect

        async def _per_row(rows: Any) -> Any:
            for row in rows:
                outcome = callback(row)
                if inspect.isawaitable(outcome):
                    outcome = await outcome
                if outcome is False:
                    return False
            return None

        await self.chunk(chunk_size, _per_row)

    def with_count(self, relation: str, alias: str | None = None) -> Self:
        """Add a ``{relation}_count`` column counting the related rows."""
        import sqlalchemy as sa

        count: Any = sa.func.count()
        subquery = self._correlated_aggregate(relation, count)
        self._aggregates.append(subquery.label(alias or f"{relation}_count"))
        return self

    def with_sum(self, relation: str, column: str, alias: str | None = None) -> Self:
        """Add a ``{relation}_sum`` column summing ``column`` over related rows (COALESCE 0)."""
        import sqlalchemy as sa

        related_table = self._relation(relation).related.__table__
        summed: Any = sa.func.coalesce(sa.func.sum(related_table.c[column]), 0)
        subquery = self._correlated_aggregate(relation, summed)
        self._aggregates.append(subquery.label(alias or f"{relation}_sum"))
        return self

    def with_avg(self, relation: str, column: str, alias: str | None = None) -> Self:
        """Add a ``{relation}_avg`` column averaging ``column`` over related rows."""
        import sqlalchemy as sa

        related_table = self._relation(relation).related.__table__
        averaged: Any = sa.func.coalesce(sa.func.avg(related_table.c[column]), 0)
        subquery = self._correlated_aggregate(relation, averaged)
        self._aggregates.append(subquery.label(alias or f"{relation}_avg"))
        return self

    def with_exists(self, relation: str, alias: str | None = None) -> Self:
        """Add a boolean ``{relation}_exists`` column (does the parent have any related row)."""
        self._aggregates.append(
            self._has_subquery(relation, None).label(alias or f"{relation}_exists")
        )
        return self

    def where_belongs_to(self, parent: Any, foreign_key: str | None = None) -> Self:
        """Constrain to children of ``parent`` (``{parent}_id`` == parent's key)."""
        from arvel.support import Str

        parent_cls = cast("Any", type(parent))  # funnel through Any: model attrs are dynamic
        fk = foreign_key or f"{Str.snake(parent_cls.__name__)}_id"
        return self.where(fk, "=", parent._attributes[parent_cls.__primary_key__])

    def latest(self, column: str = "created_at") -> Self:
        """Order newest-first by ``column``."""
        return self.order_by(column, "desc")

    def oldest(self, column: str = "created_at") -> Self:
        """Order oldest-first by ``column``."""
        return self.order_by(column, "asc")

    def doesnt_have(self, relation: str, *, connector: str = "and") -> Self:
        """Constrain to parents that have no related rows."""
        import sqlalchemy as sa

        self._add(sa.not_(self._has_subquery(relation, None)), connector)
        return self

    def where_null(self, column: str) -> Self:
        self._add(self._where_column(column).is_(None))
        return self

    def where_not_null(self, column: str) -> Self:
        self._add(self._where_column(column).is_not(None))
        return self

    def where_column(
        self, first: str, operator: str, second: str | None = None, *, connector: str = "and"
    ) -> Self:
        """``WHERE`` comparing two **columns**, e.g.
        ``where_column("updated_at", ">", "created_at")``. The 2-arg form
        (``where_column("a", "b")``) implies ``=``. Either side may be ``"other_table.col"`` to
        compare against a joined table."""
        if second is None:
            second, operator = operator, "="
        left, right = self._column_ref(first), self._column_ref(second)
        clause = (
            left.like(right) if operator == "like" else getattr(left, _COMPARISONS[operator])(right)
        )
        self._add(clause, connector)
        return self

    def where_date(self, column: str, operator: str, value: Any, *, connector: str = "and") -> Self:
        """``WHERE`` on just the DATE portion of a datetime column —
        cross-dialect via SQL ``date(...)`` (Postgres/MySQL/SQLite all support it)."""
        import sqlalchemy as sa

        expr = sa.func.date(self._table.c[column])
        self._add(self._value_comparison(expr, operator, self._date_operand(value)), connector)
        return self

    def where_time(self, column: str, operator: str, value: Any, *, connector: str = "and") -> Self:
        """``WHERE`` on just the TIME portion of a datetime column —
        cross-dialect via SQL ``time(...)``."""
        import sqlalchemy as sa

        expr = sa.func.time(self._table.c[column])
        self._add(self._value_comparison(expr, operator, value), connector)
        return self

    def where_year(self, column: str, operator: str, value: Any, *, connector: str = "and") -> Self:
        """``WHERE`` on the YEAR of a datetime column — via SQL
        ``EXTRACT(year FROM...)``."""
        return self._where_date_part("year", column, operator, value, connector=connector)

    def where_month(
        self, column: str, operator: str, value: Any, *, connector: str = "and"
    ) -> Self:
        """``WHERE`` on the MONTH of a datetime column."""
        return self._where_date_part("month", column, operator, value, connector=connector)

    def where_day(self, column: str, operator: str, value: Any, *, connector: str = "and") -> Self:
        """``WHERE`` on the DAY-of-month of a datetime column."""
        return self._where_date_part("day", column, operator, value, connector=connector)

    def _where_date_part(
        self, part: str, column: str, operator: str, value: Any, *, connector: str
    ) -> Self:
        import sqlalchemy as sa

        expr = sa.extract(part, self._table.c[column])
        self._add(self._value_comparison(expr, operator, value), connector)
        return self

    @staticmethod
    def _date_operand(value: Any) -> Any:
        """``where_date`` compares against a plain calendar date — narrow an arvel ``Date``/stdlib
        ``datetime`` down to its date portion so it compares correctly against SQL ``date(...)``."""
        import datetime as _dt

        from arvel.dates import Date

        if isinstance(value, Date):
            return value.raw.to_tz("UTC").to_stdlib().date()
        if isinstance(value, _dt.datetime):
            return value.date()
        return value

    # --- joins ---------------------------------------------------------------
    def join(
        self, table: str, first: str, operator: str, second: str, *, type_: str = "inner"
    ) -> Self:
        """SQL ``JOIN``: ``first``/``second`` are ``"table.column"`` (or a bare
        column, resolved against this query's own table). Built as a real SQLAlchemy Core
        ``Table.join()`` on the ``FROM`` clause — not a raw string. The default select stays
        ``SELECT <this table>.*``; pull in joined columns with ``select_raw("other.col")``."""
        self._joins.append((table, first, operator, second, type_))
        return self

    def left_join(self, table: str, first: str, operator: str, second: str) -> Self:
        return self.join(table, first, operator, second, type_="left")

    def right_join(self, table: str, first: str, operator: str, second: str) -> Self:
        return self.join(table, first, operator, second, type_="right")

    def _apply_joins(self, stmt: Any) -> Any:
        import sqlalchemy as sa

        from_clause: Any = self._table
        for table_name, first, operator, second, kind in self._joins:
            right = sa.table(table_name)
            onclause = getattr(self._column_ref(first), _COMPARISONS[operator])(
                self._column_ref(second)
            )
            if kind == "right":
                # SQLAlchemy Core has no RIGHT JOIN primitive — a right join is a left join with
                # the two sides swapped (semantically identical; matches the rightJoin).
                from_clause = right.join(from_clause, onclause, isouter=True)
            else:
                from_clause = from_clause.join(right, onclause, isouter=(kind == "left"))
        return stmt.select_from(from_clause)

    # --- having (post-group_by, doc B3) --------------------------------------
    def having(self, column: str, operator: str, value: Any, *, connector: str = "and") -> Self:
        """A ``HAVING`` predicate over a grouped/aggregate column — e.g.
        ``.group_by("user_id").select_raw("count(*) AS total").having("total", ">", 5)``."""
        col = self._column_or_literal(column)
        clause = (
            col.like(value)
            if operator == "like"
            else getattr(col, _COMPARISONS[operator])(self._bind(value))
        )
        self._havings.append((connector, clause))
        return self

    def having_raw(self, sql: str, bindings: Sequence[Any] = (), *, connector: str = "and") -> Self:
        """A raw ``HAVING`` predicate for an aggregate comparison the
        structural ``having()`` can't express, e.g. ``having_raw("COUNT(*) > ?", [5])``. ``?``
        placeholders bind positionally. The SQL itself is trusted — never interpolate user input;
        pass values through ``bindings``."""
        import sqlalchemy as sa

        params: dict[str, Any] = {}
        for i, val in enumerate(bindings):
            name = f"_having_{i}"
            sql = sql.replace("?", f":{name}", 1)
            params[name] = val
        clause: Any = sa.text(sql).bindparams(**params) if params else sa.text(sql)
        self._havings.append((connector, clause))
        return self

    def _having_expression(self) -> Any:
        import sqlalchemy as sa

        expr: Any = None
        for connector, clause in self._havings:
            if expr is None:
                expr = clause
            elif connector == "or":
                expr = sa.or_(expr, clause)
            else:
                expr = sa.and_(expr, clause)
        return expr

    # --- shaping -----------------------------------------------------------
    def select(self, *columns: str) -> Self:
        self._columns = list(columns)
        return self

    def select_raw(self, expression: str) -> Self:
        """Add a raw SQL select expression (e.g. ``"sum(total) AS revenue"``) — for aggregates
        and computed columns that ``select()`` can't name. Used with ``group_by`` (spec 08 §42).
        When present without ``select()``, it replaces the default ``SELECT *``."""
        import sqlalchemy as sa

        self._raw_selects.append(sa.literal_column(expression))
        return self

    def group_by(self, *columns: str) -> Self:
        """Group rows by one or more columns/aliases for aggregate queries (spec 08 §42)."""
        self._group_by.extend(columns)
        return self

    def distinct(self) -> Self:
        self._distinct = True
        return self

    def order_by(self, column: str, direction: str = "asc") -> Self:
        col = self._where_column(column)
        self._order.append(col.desc() if direction == "desc" else col.asc())
        self._order_specs.append((column, direction))
        return self

    def order_by_raw(self, sql: str) -> Self:
        """A raw ``ORDER BY`` expression, e.g. a ``CASE``/``FIELD()``
        custom ordering the structural ``order_by`` can't express. Not tracked in
        ``cursor_paginate``'s keyset ordering — pair it with an explicit ``order_by`` tiebreaker
        if you need seekable pages."""
        import sqlalchemy as sa

        self._order.append(sa.text(sql))
        return self

    def limit(self, count: int) -> Self:
        self._limit = count
        return self

    def offset(self, count: int) -> Self:
        self._offset = count
        return self

    def take(self, count: int) -> Self:
        """alias for ``limit``."""
        return self.limit(count)

    def skip(self, count: int) -> Self:
        """alias for ``offset``."""
        return self.offset(count)

    def lock_for_update(self) -> Self:
        self._lock = "update"
        return self

    def shared_lock(self) -> Self:
        self._lock = "shared"
        return self

    # --- CTEs (doc 08) -------------------------------------------------------
    def to_cte(self, name: str, *, recursive: bool = False) -> Any:
        """This query as a SQLAlchemy Core CTE (``WITH``)."""
        return self.to_select().cte(name, recursive=recursive)

    def recursive_cte(self, name: str, anchor: Builder, recursive: Callable[[Any], Any]) -> Any:
        """A ``WITH RECURSIVE`` query: ``anchor`` is the base term; ``recursive`` receives
        the CTE and returns the recursive Core ``Select`` term (doc 08)."""
        import sqlalchemy as sa

        base = anchor.to_select().cte(name, recursive=True)
        return sa.select(base.union_all(recursive(base)))

    def from_cte(self, cte: Any) -> Self:
        """Re-source this builder onto a CTE/selectable (so ``.get()`` reads from it). D6."""
        self._table = cte
        return self

    # --- Core construct builders (G4: real statement objects, not strings) ---
    def _where_expression(self) -> Any:
        import sqlalchemy as sa

        expr: Any = None
        for connector, clause in self._wheres:
            if expr is None:
                expr = clause
            elif connector == "or":
                expr = sa.or_(expr, clause)
            else:
                expr = sa.and_(expr, clause)
        return expr

    def _select_targets(self) -> list[Any]:
        import sqlalchemy as sa

        targets: list[Any] = []
        if self._columns:
            targets.extend(self._column_ref(c) for c in self._columns)
        targets.extend(self._raw_selects)
        if not targets:  # no select()/select_raw() → the whole table (SELECT *)
            # a bare table clause (DB.table over a table/view with no declared columns) → SELECT *
            targets.append(self._table if len(self._table.c) else sa.literal_column("*"))
        return [*targets, *self._aggregates]

    def _group_targets(self) -> list[Any]:
        return [self._column_or_literal(name) for name in self._group_by]

    def to_select(self) -> Any:
        import sqlalchemy as sa

        stmt = sa.select(*self._select_targets())
        if self._joins:  # the joined construct IS the FROM (subsumes the plain-table case below)
            stmt = self._apply_joins(stmt)
        elif self._raw_selects or not len(self._table.c):  # raw/`*` carry no table ref → pin FROM
            stmt = stmt.select_from(self._table)
        if self._distinct:
            stmt = stmt.distinct()
        expr = self._where_expression()
        if expr is not None:
            stmt = stmt.where(expr)
        if self._group_by:
            stmt = stmt.group_by(*self._group_targets())
        having = self._having_expression()
        if having is not None:
            stmt = stmt.having(having)
        for clause in self._order:
            stmt = stmt.order_by(clause)
        if self._limit is not None:
            stmt = stmt.limit(self._limit)
        if self._offset is not None:
            stmt = stmt.offset(self._offset)
        if self._lock == "update":
            stmt = stmt.with_for_update()
        elif self._lock == "shared":
            stmt = stmt.with_for_update(read=True)
        return stmt

    def to_insert(self, values: dict[str, Any]) -> Any:
        import sqlalchemy as sa

        return sa.insert(self._table).values(**values)

    def to_update(self, values: dict[str, Any]) -> Any:
        import sqlalchemy as sa

        # same value-object adaptation as where() (e.g. Date -> UTC stdlib datetime)
        bound = {column: self._bind(value) for column, value in values.items()}
        stmt = sa.update(self._table).values(**bound)
        expr = self._where_expression()
        if expr is not None:
            stmt = stmt.where(expr)
        return stmt

    def to_delete(self) -> Any:
        import sqlalchemy as sa

        stmt = sa.delete(self._table)
        expr = self._where_expression()
        if expr is not None:
            stmt = stmt.where(expr)
        return stmt

    # --- execution ---------------------------------------------------------
    def _require_resolver(self) -> ConnectionResolver:
        if self._resolver is None:
            raise RuntimeError("Builder has no connection resolver bound.")
        return self._resolver

    async def get(self) -> Any:
        """Every matching row. A **hydrating** (model-bound) query returns an
        :class:`~arvel.database.collection.EloquentCollection` (doc B3); a raw table builder (no
                ``hydrate``) returns a plain ``list[dict]`` — the query builder returns a Collection
                too, but arvel keeps raw rows as plain dicts (typed simplicity over exact parity)."""
        rows = await self._require_resolver().fetch_all(self.to_select())
        records = [dict(row) for row in rows]
        if self._hydrate is None:
            return records
        models = [await _maybe_await(self._hydrate(r)) for r in records]
        for spec in self._eager:
            await self._eager_load_path(models, spec.split("."), self._eager_constraints.get(spec))
        from arvel.database.collection import EloquentCollection

        return EloquentCollection(models)

    async def upsert(
        self, rows: list[dict[str, Any]], unique_by: list[str], update: list[str] | None = None
    ) -> Any:
        """Insert ``rows``; on a conflict over ``unique_by``, update ``update`` columns (defaults
                to all non-key columns). Dialect-aware: Postgres/SQLite use ``ON CONFLICT DO UPDATE``;
                MySQL/MariaDB use ``ON DUPLICATE KEY UPDATE`` (``unique_by`` is implicit there — MySQL has
                no ``ON CONFLICT(cols)`` targeting, so it's honored by documentation only, matching
        , which ignores ``$uniqueBy`` on MySQL too). An unrecognized dialect raises
        :class:`UnsupportedDriverOperation` rather than silently emitting the wrong SQL (A4)."""
        import importlib

        resolver = self._require_resolver()
        dialect = resolver.engine().dialect.name
        columns = update or [c for c in rows[0] if c not in unique_by]

        if dialect in ("postgresql", "sqlite"):
            dialect_dml: Any = importlib.import_module(f"sqlalchemy.dialects.{dialect}")
            statement = dialect_dml.insert(self._table).values(rows)
            statement = statement.on_conflict_do_update(
                index_elements=unique_by,
                set_={c: statement.excluded[c] for c in columns},
            )
        elif dialect in ("mysql", "mariadb"):
            from sqlalchemy.dialects.mysql import insert as mysql_insert

            statement = mysql_insert(self._table).values(rows)
            statement = statement.on_duplicate_key_update(
                **{c: statement.inserted[c] for c in columns}
            )
        else:
            raise UnsupportedDriverOperation(
                f"upsert() has no ON CONFLICT/ON DUPLICATE KEY implementation for the "
                f"{dialect!r} dialect."
            )
        return await resolver.execute(statement)

    async def cursor(self) -> AsyncIterator[Any]:
        """Stream results one model at a time (low memory; server-side cursor)."""
        rows: Any = self._require_resolver().stream(self.to_select())
        async for row in rows:
            yield (await _maybe_await(self._hydrate(row))) if self._hydrate is not None else row

    async def lazy(self) -> AsyncIterator[Any]:
        """Lazily stream results (alias of ``cursor`` — yields models one by one)."""
        async for model in self.cursor():
            yield model

    async def _eager_load_path(
        self, models: list[Any], segments: list[str], constrain: Any = None
    ) -> None:
        """Load a (possibly nested) eager path like ``posts.comments`` across ``models``.
        ``constrain`` (a callback) restricts the *first* segment's related rows (D2)."""
        if not models or not segments:
            return
        name = segments[0]
        relation = getattr(models[0], name)()
        if constrain is not None:
            await relation.eager_load(models, name, constrain)
        else:
            await relation.eager_load(models, name)
        if len(segments) > 1:  # descend into the freshly-loaded related models
            from arvel.support import Collection

            nested: list[Any] = []
            for model in models:
                loaded = model._relations.get(name)
                if isinstance(
                    loaded, (list, Collection)
                ):  # a many-relation: list or EloquentCollection
                    nested.extend(cast("list[Any]", loaded))
                elif loaded is not None:
                    nested.append(loaded)
            await self._eager_load_path(nested, segments[1:])

    async def first(self) -> Any:
        row = await self._require_resolver().fetch_one(self.to_select())
        if row is None:
            return None
        record = dict(row)
        if self._hydrate is None:
            return record
        model = await _maybe_await(self._hydrate(record))
        # parity: ``with('rel')->first()`` eager-loads the relation, just like ``get()``.
        for spec in self._eager:
            await self._eager_load_path([model], spec.split("."), self._eager_constraints.get(spec))
        return model

    async def first_or_fail(self) -> Any:
        """``first()`` or raise ``ModelNotFound``."""
        row = await self.first()
        if row is None:
            from arvel.database.model import ModelNotFound

            name = self._model.__name__ if self._model is not None else self._table.name
            raise ModelNotFound(f"No query results for model [{name}].")
        return row

    @staticmethod
    def _column_of(row: Any, column: str) -> Any:
        if isinstance(row, dict):
            return cast("dict[str, Any]", row)[column]
        return getattr(row, column)

    async def value(self, column: str) -> Any:
        """The given column from the first matching row, or ``None``."""
        row = await self.first()
        return None if row is None else self._column_of(row, column)

    async def pluck(self, column: str, key: str | None = None) -> Any:
        """A list of a single column's values — or a ``{key: column}`` dict when ``key`` is
        given."""
        rows = await self.get()
        if key is not None:
            return {self._column_of(r, key): self._column_of(r, column) for r in rows}
        return [self._column_of(r, column) for r in rows]

    async def insert(self, values: dict[str, Any]) -> WriteResult:
        return await self._require_resolver().execute(self.to_insert(values))

    async def update(self, values: dict[str, Any]) -> WriteResult:
        return await self._require_resolver().execute(self.to_update(values))

    async def delete(self) -> WriteResult:
        return await self._require_resolver().execute(self.to_delete())

    # --- aggregates --------------------------------------------------------
    async def count(self) -> int:
        import sqlalchemy as sa

        stmt = sa.select(sa.func.count()).select_from(self._table)
        expr = self._where_expression()
        if expr is not None:
            stmt = stmt.where(expr)
        return int(await self._require_resolver().scalar(stmt) or 0)

    async def _aggregate(self, fn: str, column: str) -> Any:
        import sqlalchemy as sa

        stmt = sa.select(getattr(sa.func, fn)(self._table.c[column]))
        expr = self._where_expression()
        if expr is not None:
            stmt = stmt.where(expr)
        return await self._require_resolver().scalar(stmt)

    async def sum(self, column: str) -> Any:
        return await self._aggregate("sum", column)

    async def avg(self, column: str) -> Any:
        return await self._aggregate("avg", column)

    async def min(self, column: str) -> Any:
        return await self._aggregate("min", column)

    async def max(self, column: str) -> Any:
        return await self._aggregate("max", column)

    async def exists(self) -> bool:
        return await self.first() is not None

    async def paginate(self, per_page: int = 15, page: int | None = None) -> LengthAwarePaginator:
        """A length-aware paginator: runs a ``count`` for the grand total
        so it can render a full numbered page list. ``page`` defaults to the current request's
        ``?page=`` (1 outside a request)."""
        from arvel.pagination import LengthAwarePaginator, resolve_current_page

        per_page = max(1, per_page)
        if page is None:
            page = resolve_current_page()
        total = await self.count()
        self.limit(per_page).offset((page - 1) * per_page)
        data = await self.get()
        return LengthAwarePaginator(data, total, per_page, page)

    async def simple_paginate(self, per_page: int = 15, page: int | None = None) -> Paginator:
        """A lean prev/next paginator: no ``count`` query — it fetches
        one extra row to know whether a *next* page exists. ``page`` defaults to ``?page=``."""
        from arvel.pagination import Paginator, resolve_current_page

        per_page = max(1, per_page)
        if page is None:
            page = resolve_current_page()
        self.limit(per_page + 1).offset((page - 1) * per_page)
        data = await self.get()
        return Paginator(data, per_page, page)

    # --- cursor (keyset) pagination -----------------------------------------------------------
    def _coerce_cursor_value(self, column: str, value: Any) -> Any:
        """A decoded cursor value round-trips over JSON as a plain str/int/bool — parse a
        datetime/date column's value back from its ISO string so binding stays type-correct."""
        import datetime as _dt

        import sqlalchemy as sa

        if not isinstance(value, str):
            return value
        col_type = self._table.c[column].type
        if isinstance(col_type, sa.DateTime):
            return _dt.datetime.fromisoformat(value)
        if isinstance(col_type, sa.Date):
            return _dt.date.fromisoformat(value)
        return value

    def _seek_predicate(self, specs: list[tuple[str, str]], position: dict[str, Any]) -> Any:
        """The keyset ``WHERE`` clause: rows strictly after ``position`` in the lexicographic
        order of ``specs`` — ``(col1 > v1) OR (col1 = v1 AND col2 > v2) OR...`` — the standard,
        fully-portable seek predicate (no ``ROW()`` comparison needed)."""
        import sqlalchemy as sa

        clauses: list[Any] = []
        for i, (column, direction) in enumerate(specs):
            equals = [
                self._table.c[c] == self._coerce_cursor_value(c, position[c]) for c, _ in specs[:i]
            ]
            col = self._table.c[column]
            bound = self._coerce_cursor_value(column, position[column])
            tie = col > bound if direction == "asc" else col < bound
            clauses.append(sa.and_(*equals, tie) if equals else tie)
        return sa.or_(*clauses)

    def _cursor_boundary(self, row: Any, specs: list[tuple[str, str]]) -> dict[str, Any]:
        return {column: self._column_of(row, column) for column, _ in specs}

    async def cursor_paginate(
        self, per_page: int = 15, cursor: str | None = None
    ) -> CursorPaginator:
        """A keyset (cursor) paginator: seeks past the last row's
        ordering values instead of ``OFFSET``, so pages stay correct even when rows are inserted
        before the cursor mid-scan — the "page drift" ``paginate()``/``simple_paginate()`` can't
        avoid. Requires an ``order_by`` (defaults to the primary key ascending); the primary key is
        always appended as a tiebreaker if not already part of the ordering, so paging over a
        non-unique column stays stable. The opaque ``cursor`` — pass back
        ``CursorPaginator.next_cursor()``/``.previous_cursor()`` to walk forward/back — is a
        base64 encoding of the ordering columns' values at the seek point (DR-0022 object shape)."""
        from arvel.pagination import CursorPaginator, decode_cursor, encode_cursor

        per_page = max(1, per_page)
        pk = self._model.__primary_key__ if self._model is not None else "id"
        if not self._order_specs:
            self.order_by(pk, "asc")
        if pk not in [c for c, _ in self._order_specs]:
            self.order_by(pk, "asc")
        specs = list(self._order_specs)

        position: dict[str, Any] | None = None
        backward = False
        if cursor is not None:
            position, backward = decode_cursor(cursor)

        scan_specs = [(c, ("desc" if d == "asc" else "asc") if backward else d) for c, d in specs]
        if position is not None:
            self._add(self._seek_predicate(scan_specs, position))
        self._order = [
            (self._table.c[c].desc() if d == "desc" else self._table.c[c].asc())
            for c, d in scan_specs
        ]

        self._limit = per_page + 1
        rows = await self.get()
        has_extra = len(rows) > per_page
        page_rows = list(rows[:per_page])
        if backward:
            page_rows.reverse()  # scanned in reverse to seek backward; restore natural order

        next_cursor: str | None = None
        prev_cursor: str | None = None
        if page_rows:
            if backward:
                next_cursor = encode_cursor(self._cursor_boundary(page_rows[-1], specs))
                if has_extra:
                    prev_cursor = encode_cursor(
                        self._cursor_boundary(page_rows[0], specs), backward=True
                    )
            else:
                if position is not None:
                    prev_cursor = encode_cursor(
                        self._cursor_boundary(page_rows[0], specs), backward=True
                    )
                if has_extra:
                    next_cursor = encode_cursor(self._cursor_boundary(page_rows[-1], specs))

        return CursorPaginator(
            page_rows, per_page, next_cursor=next_cursor, prev_cursor=prev_cursor
        )
