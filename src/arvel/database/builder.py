"""arvel.database.builder — the query builder on SQLAlchemy Core.

The G4-load-bearing piece: ``Builder`` composes **SQLAlchemy Core construct
objects** (``select()``/``insert()``/``update()``/``delete()`` + ``and_()``/``or_()``
over ``Table``/``Column`` metadata) — never raw SQL strings — so the *same* builder
call compiles correctly to every dialect. SQLAlchemy is lazy-imported. *Lazy-import ≠
reimplement* (doc 00 §5b). Grounded in knowledge/port/07-orm-active-record.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self, cast

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Sequence

    from sqlalchemy import Select

    from arvel.database.connections import ConnectionResolver, WriteResult
    from arvel.pagination import LengthAwarePaginator, Paginator

_COMPARISONS = {
    "=": "__eq__",
    "==": "__eq__",
    "!=": "__ne__",
    ">": "__gt__",
    ">=": "__ge__",
    "<": "__lt__",
    "<=": "__le__",
}


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
        self._columns: list[str] | None = None
        self._raw_selects: list[Any] = []  # select_raw() expressions (spec 08 §42)
        self._group_by: list[str] = []  # group_by() column / alias names
        self._distinct = False
        self._limit: int | None = None
        self._offset: int | None = None
        self._eager: list[str] = []
        self._eager_constraints: dict[str, Any] = {}  # per-relation constrained eager load (D2)
        self._lock: str | None = None
        self._aggregates: list[Any] = []  # labeled scalar subqueries (with_count/with_sum)

    def __getattr__(self, name: str) -> Any:
        # Resolve local scopes: a model method `scope_<name>` is callable as `.<name>(...)`.
        # Only kicks in for genuinely-missing attributes; everything else is a real error.
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
        dropping to ``.to_py()`` (Laravel accepts a Carbon directly). Other values pass through."""
        from arvel.dates import Date

        return value.raw.to_tz("UTC").to_stdlib() if isinstance(value, Date) else value

    def _comparison(self, column: str, operator: str, value: Any) -> Any:
        col = self._table.c[column]
        if operator == "like":
            return col.like(value)
        if operator == "in":
            return col.in_([self._bind(v) for v in value])
        return getattr(col, _COMPARISONS[operator])(self._bind(value))

    def _apply_conditions(
        self, args: tuple[Any, ...], kwargs: dict[str, Any], connector: str
    ) -> None:
        for column, val in kwargs.items():
            self._add(self._table.c[column] == self._bind(val), connector)
        if len(args) == 2:
            self._add(self._table.c[args[0]] == self._bind(args[1]), connector)
        elif len(args) == 3:
            self._add(self._comparison(args[0], args[1], args[2]), connector)

    def where(self, *args: Any, **kwargs: Any) -> Self:
        self._apply_conditions(args, kwargs, "and")
        return self

    def or_where(self, *args: Any, **kwargs: Any) -> Self:
        self._apply_conditions(args, kwargs, "or")
        return self

    def where_in(self, column: str, values: Sequence[Any] | Select[Any]) -> Self:
        """``WHERE col IN (...)``. ``values`` is a list **or a subquery** ``Select`` (Laravel
        ``whereIn('id', $subquery)``) — pass ``sa.select(other.c.id)`` to filter DB-side without
        materializing the id list in the app (e.g. ``where_in('id', select(retrievable.c.id))``)."""
        self._add(self._table.c[column].in_(values))
        return self

    def where_not_in(self, column: str, values: Sequence[Any] | Select[Any]) -> Self:
        self._add(self._table.c[column].not_in(values))
        return self

    def or_where_in(self, column: str, values: Sequence[Any]) -> Self:
        self._add(self._table.c[column].in_(values), "or")
        return self

    def where_between(self, column: str, values: Sequence[Any]) -> Self:
        low, high = values
        self._add(self._table.c[column].between(low, high))
        return self

    def where_not_between(self, column: str, values: Sequence[Any]) -> Self:
        import sqlalchemy as sa

        low, high = values
        self._add(sa.not_(self._table.c[column].between(low, high)))
        return self

    def _apply_conditional(self, callback: Any, value: Any) -> None:
        """Invoke a ``when``/``unless`` callback Laravel-style. Laravel passes ``($query, $value)``;
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
        """Laravel ``when`` — apply ``callback(self, condition)`` only if ``condition`` is truthy,
        else ``default(self, condition)`` if given. Lets conditional clauses stay in the fluent chain.

        Matches Laravel's ``when($value, fn($query, $value))``: the truthy value is passed to the
        callback's 2nd argument. A 1-arg callback (``lambda q: ...``, closing over the value
        directly) also works — the value is only passed when the callback accepts it.
        """
        if condition:
            self._apply_conditional(callback, condition)
        elif default is not None:
            self._apply_conditional(default, condition)
        return self

    def unless(self, condition: Any, callback: Any, default: Any = None) -> Self:
        """Laravel ``unless`` — the inverse of ``when``: apply ``callback(self, condition)`` only
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
        """Filter on a value *inside* a JSON column — Laravel ``where('data->lang', 'en')``.
        ``path`` is a key, a nested ``a->b`` / ``a.b`` path, or an array index. Compares the
        extracted value as text, so it works across SQLite and Postgres."""
        self._add(self._json_path(column, path).as_string() == value, connector)
        return self

    def where_json_like(
        self, column: str, path: str, value: str, *, connector: str = "and"
    ) -> Self:
        """``LIKE`` against a value inside a JSON column — Laravel ``where('data->name', 'like', '%x%')``.
        Handy for searching a per-locale translatable attribute, e.g.
        ``where_json_like('name', 'en', '%phone%')``. Cross-dialect (json_extract / ``->>``)."""
        self._add(self._json_path(column, path).as_string().like(value), connector)
        return self

    def where_json_contains(self, column: str, value: Any, *, connector: str = "and") -> Self:
        """Postgres/MySQL JSON containment — Laravel ``whereJsonContains('data->tags', 'x')``:
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
        """Postgres full-text search — Laravel ``whereFullText``: rows whose ``column`` matches
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
        that *same* constraint (Laravel ``withWhereHas`` parity — one constraint, both
        effects). D2."""
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
        last: Any = 0
        while True:
            self._wheres = [*base_wheres, ("and", self._table.c[key] > last)]
            self._order = [self._table.c[key].asc()]
            self._limit = size
            rows = await self.get()
            if not rows:
                return
            outcome = callback(rows)
            if inspect.isawaitable(outcome):
                await outcome
            tail = rows[-1]
            last = tail._attributes[key] if hasattr(tail, "_attributes") else tail[key]
            if len(rows) < size:
                return

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
        self._add(self._table.c[column].is_(None))
        return self

    def where_not_null(self, column: str) -> Self:
        self._add(self._table.c[column].is_not(None))
        return self

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
        col = self._table.c[column]
        self._order.append(col.desc() if direction == "desc" else col.asc())
        return self

    def limit(self, count: int) -> Self:
        self._limit = count
        return self

    def offset(self, count: int) -> Self:
        self._offset = count
        return self

    def take(self, count: int) -> Self:
        """Laravel alias for ``limit``."""
        return self.limit(count)

    def skip(self, count: int) -> Self:
        """Laravel alias for ``offset``."""
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
        targets: list[Any] = []
        if self._columns:
            targets.extend(self._table.c[c] for c in self._columns)
        targets.extend(self._raw_selects)
        if not targets:  # no select()/select_raw() → the whole table (SELECT *)
            targets.append(self._table)
        return [*targets, *self._aggregates]

    def _group_targets(self) -> list[Any]:
        import sqlalchemy as sa

        cols = self._table.c
        return [cols[name] if name in cols else sa.literal_column(name) for name in self._group_by]

    def to_select(self) -> Any:
        import sqlalchemy as sa

        stmt = sa.select(*self._select_targets())
        if self._raw_selects:  # raw columns carry no table ref → pin the FROM explicitly
            stmt = stmt.select_from(self._table)
        if self._distinct:
            stmt = stmt.distinct()
        expr = self._where_expression()
        if expr is not None:
            stmt = stmt.where(expr)
        if self._group_by:
            stmt = stmt.group_by(*self._group_targets())
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

        # Adapt value-object bind values (e.g. an arvel Date → its UTC stdlib datetime) the same way
        # where() does, so `update({"published_at": Date.now()})` works without dropping to .to_py().
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

    async def get(self) -> list[Any]:
        rows = await self._require_resolver().fetch_all(self.to_select())
        records = [dict(row) for row in rows]
        if self._hydrate is None:
            return records
        models = [self._hydrate(r) for r in records]
        for spec in self._eager:
            await self._eager_load_path(models, spec.split("."), self._eager_constraints.get(spec))
        return models

    async def upsert(
        self, rows: list[dict[str, Any]], unique_by: list[str], update: list[str] | None = None
    ) -> Any:
        """Insert ``rows``; on a conflict over ``unique_by``, update ``update`` columns
        (defaults to all non-key columns). Dialect-aware ON CONFLICT (Core, doc 07)."""
        import importlib

        resolver = self._require_resolver()
        # ON CONFLICT lives on the dialect-specific insert(); load it by name so the two
        # branches don't collide in the type-checker (pg + sqlite share the same API).
        name = "postgresql" if resolver.engine().dialect.name == "postgresql" else "sqlite"
        dialect_dml: Any = importlib.import_module(f"sqlalchemy.dialects.{name}")
        statement = dialect_dml.insert(self._table).values(rows)
        columns = update or [c for c in rows[0] if c not in unique_by]
        statement = statement.on_conflict_do_update(
            index_elements=unique_by,
            set_={c: statement.excluded[c] for c in columns},
        )
        return await resolver.execute(statement)

    async def cursor(self) -> AsyncIterator[Any]:
        """Stream results one model at a time (low memory; server-side cursor)."""
        rows: Any = self._require_resolver().stream(self.to_select())
        async for row in rows:
            yield self._hydrate(row) if self._hydrate is not None else row

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
            nested: list[Any] = []
            for model in models:
                loaded = model._relations.get(name)
                if isinstance(loaded, list):
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
        model = self._hydrate(record)
        # Laravel parity: ``with('rel')->first()`` eager-loads the relation, just like ``get()``.
        for spec in self._eager:
            await self._eager_load_path([model], spec.split("."), self._eager_constraints.get(spec))
        return model

    async def first_or_fail(self) -> Any:
        """``first()`` or raise ``ModelNotFound`` (Laravel ``firstOrFail``)."""
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
        """The given column from the first matching row, or ``None`` (Laravel ``value``)."""
        row = await self.first()
        return None if row is None else self._column_of(row, column)

    async def pluck(self, column: str, key: str | None = None) -> Any:
        """A list of a single column's values — or a ``{key: column}`` dict when ``key`` is
        given (Laravel ``pluck``)."""
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
        """A length-aware paginator (Laravel ``paginate``): runs a ``count`` for the grand total
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
        """A lean prev/next paginator (Laravel ``simplePaginate``): no ``count`` query — it fetches
        one extra row to know whether a *next* page exists. ``page`` defaults to ``?page=``."""
        from arvel.pagination import Paginator, resolve_current_page

        per_page = max(1, per_page)
        if page is None:
            page = resolve_current_page()
        self.limit(per_page + 1).offset((page - 1) * per_page)
        data = await self.get()
        return Paginator(data, per_page, page)
