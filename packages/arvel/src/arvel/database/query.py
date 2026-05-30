"""Typed fluent query builder."""

from __future__ import annotations

import base64
import contextlib
import json
import uuid as _uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, Generic, Protocol, Self, TypeGuard, TypeVar, cast

from sqlalchemy import (
    Select,
    Table,
    desc,
    func,
    select,
    text,
)
from sqlalchemy import (
    cast as sqla_cast,
)
from sqlalchemy import (
    inspect as sqla_inspect,
)
from sqlalchemy.dialects.postgresql import REGCONFIG
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import InstrumentedAttribute, Mapper, selectinload

from arvel.database.exceptions import (
    ModelNotFoundError,
    MultipleResultsError,
    UnknownRelationError,
)
from arvel.database.paginator import Paginator
from arvel.database.session import get_active_session

if TYPE_CHECKING:
    from sqlalchemy.sql.expression import CTE

    from arvel.database.orm.belongs_to_many import BelongsToManyLink
    from arvel.database.query_mixin import QueryMixin

T = TypeVar("T", bound="QueryMixin")
# Separate, unbound TypeVar for the standalone paginator containers. They hold
# items and serialize them; they never call QueryMixin methods on T, so there's
# no reason to inherit the QueryMixin bound from QueryBuilder.
TItem = TypeVar("TItem")


class _ModelFactory(Protocol):
    async def create(self, **attrs: Any) -> Any: ...


class _SaveableModel(Protocol):
    async def save(self) -> object: ...


_TSQUERY_FNS: frozenset[str] = frozenset(
    {"plainto_tsquery", "websearch_to_tsquery", "to_tsquery", "phraseto_tsquery"}
)

_WHERE_ANY_OPS: frozenset[str] = frozenset({"=", "like", "ilike", ">", "<", ">=", "<=", "!="})


def _apply_operator(col: Any, operator: str, value: Any) -> Any:
    """Map an operator string to a SQLAlchemy column expression."""
    dispatch: dict[str, Any] = {
        "=": col == value,
        "like": col.like(value),
        "ilike": col.ilike(value),
        ">": col > value,
        "<": col < value,
        ">=": col >= value,
        "<=": col <= value,
        "!=": col != value,
    }
    return dispatch[operator]


def _resolve_sqla_dialect(name: str | None) -> Any:
    """Return a SQLAlchemy dialect instance by name, or None for generic rendering."""
    if name is None:
        return None
    _dialect_map: dict[str, str] = {
        "sqlite": "sqlalchemy.dialects.sqlite:dialect",
        "mysql": "sqlalchemy.dialects.mysql:dialect",
        "postgresql": "sqlalchemy.dialects.postgresql:dialect",
        "postgres": "sqlalchemy.dialects.postgresql:dialect",
    }
    entry = _dialect_map.get(name.lower())
    if entry is None:
        return None
    module_path, cls_name = entry.split(":")
    import importlib

    mod = importlib.import_module(module_path)
    return getattr(mod, cls_name)()


def _resolve_column(model: type[Any], name_or_col: Any) -> InstrumentedAttribute[Any]:
    """Map a column reference (string name or InstrumentedAttribute) to an attribute."""
    if isinstance(name_or_col, str):
        col = getattr(model, name_or_col, None)
        if not isinstance(col, InstrumentedAttribute):
            raise AttributeError(f"{model.__name__}.{name_or_col} is not a column.")
        return col  # pyright: ignore[reportUnknownVariableType]
    return cast("InstrumentedAttribute[Any]", name_or_col)


def _mapper_of(model: type[Any]) -> Mapper[Any]:
    """Return the SQLAlchemy Mapper for a mapped class. Callers guarantee model is mapped."""
    return cast("Mapper[Any]", sqla_inspect(model))


def _table_of(model: type[Any]) -> Table:
    """Return the SQLAlchemy ``Table`` backing a mapped model.

    ``Model.__table__`` is typed as the broader ``FromClause`` for ORM mixin
    flexibility, but at runtime — and per SQLAlchemy's declarative contract —
    the value is always a concrete ``Table`` instance for any mapped class.
    """
    mapper: Mapper[Any] = sqla_inspect(model)
    table = mapper.local_table
    if not isinstance(table, Table):
        raise TypeError(f"{model.__name__} is not mapped to a Table.")
    return table


def _split_select_list(expr: str) -> list[str]:
    """Split a SQL SELECT list on top-level commas, respecting parentheses.

    ``"name, SUM(score, 0) as total"`` → ``["name", "SUM(score, 0) as total"]``.
    """
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in expr:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            piece = "".join(buf).strip()
            if piece:
                parts.append(piece)
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _local_remote(rel: Any) -> tuple[Any, Any]:
    """Return the first (local, remote) column pair on a SQLAlchemy relationship.

    SQLAlchemy types ``relationship.local_remote_pairs`` as a possibly-``None``
    sequence; configured relationships always populate at least one pair, so we
    surface a clear error if the contract is violated instead of letting
    ``next(iter(None))`` raise a confusing ``TypeError``.
    """
    pairs = rel.local_remote_pairs
    if not pairs:
        raise UnknownRelationError(rel.parent.class_.__name__, rel.key)
    local, remote = pairs[0]
    return local, remote


@dataclass(frozen=True)
class _RelationTarget:
    """Resolved relation — either a SQLAlchemy relationship or BelongsToMany."""

    kind: str
    sa_rel: Any | None = None
    btm_link: BelongsToManyLink | None = None


def _resolve_relation(model: type[Any], name: str | Any) -> _RelationTarget:
    if not isinstance(name, str):
        # Accept InstrumentedAttribute / QueryableAttribute — extract the key.
        name = name.key
    mapper = _mapper_of(model)
    rel = mapper.relationships.get(name)
    if rel is not None:
        return _RelationTarget(kind="sa", sa_rel=rel)

    from arvel.database.orm.belongs_to_many import BelongsToMany

    descriptor = getattr(model, name, None)
    if isinstance(descriptor, BelongsToMany):
        return _RelationTarget(kind="btm", btm_link=descriptor.link_spec())

    raise UnknownRelationError(model.__name__, name)


def _primary_key_column(model: type[Any]) -> Any:
    return _mapper_of(model).primary_key[0]


def _global_scope_whereclause(related_cls: type[Any]) -> Any:
    """Related model's global-scope predicate (e.g. soft-delete `deleted_at IS NULL`), or None."""
    scoped = QueryBuilder(related_cls, select(related_cls)).apply_global_scopes()
    return scoped.whereclause


def _exists_subquery(
    model: type[Any],
    target: _RelationTarget,
    constraint: Callable[[QueryBuilder[Any]], QueryBuilder[Any]] | None = None,
) -> Select[Any]:
    if target.kind == "sa":
        rel = target.sa_rel
        if rel is None:
            raise UnknownRelationError(model.__name__, "?")
        related_cls = rel.mapper.class_
        local_col, remote_col = _local_remote(rel)
        sub: Select[Any] = select(related_cls).where(remote_col == local_col)
    else:
        link = target.btm_link
        if link is None:
            raise UnknownRelationError(model.__name__, "?")
        pivot = link.table
        related_cls = link.related_model
        local_col = _primary_key_column(model)
        pivot_fk = pivot.c[link.foreign_key]
        pivot_rfk = pivot.c[link.related_foreign_key]
        remote_col = _primary_key_column(related_cls)
        sub = select(related_cls).join(pivot, pivot_rfk == remote_col).where(pivot_fk == local_col)

    # Honour the related model's global scopes (soft deletes) — Laravel's whereHas/has
    # never counts trashed related rows.
    sub_qb: QueryBuilder[Any] = QueryBuilder(related_cls, sub)
    if constraint is not None:
        sub_qb = constraint(sub_qb)
    return sub_qb.apply_global_scopes()


def _selectin_loader_for_path(
    model: type[Any],
    relation_path: str,
    *,
    constraint: Callable[[QueryBuilder[Any]], QueryBuilder[Any]] | None = None,
) -> Any:
    """Build a selectinload option for *relation_path*, optionally filtered."""
    mapper = _mapper_of(model)
    valid: set[str] = {r.key for r in mapper.relationships}
    head, _, tail = relation_path.partition(".")
    if head not in valid:
        raise UnknownRelationError(model.__name__, head)
    head_rel = mapper.relationships[head]
    related_cls = head_rel.mapper.class_
    head_attr: Any = getattr(model, head)
    if constraint is not None:
        sub_qb = QueryBuilder(related_cls, select(related_cls))
        sub_qb = constraint(sub_qb)
        where_clause = sub_qb.statement.whereclause
        if where_clause is not None:
            head_attr = head_attr.and_(where_clause)
    loader = selectinload(head_attr)
    cursor_mapper = head_rel.mapper
    for hop in tail.split(".") if tail else []:
        if not hop:
            continue
        cursor_attr = getattr(cursor_mapper.class_, hop, None)
        if not isinstance(cursor_attr, InstrumentedAttribute):
            raise UnknownRelationError(cursor_mapper.class_.__name__, hop)
        loader = loader.selectinload(cursor_attr)  # pyright: ignore[reportUnknownArgumentType]
        cursor_mapper = cursor_mapper.relationships[hop].mapper
    return loader


def _count_subquery(model: type[Any], target: _RelationTarget) -> Any:
    from sqlalchemy import func as sqla_func

    if target.kind == "sa":
        rel = target.sa_rel
        if rel is None:
            raise UnknownRelationError(model.__name__, "?")
        related_cls = rel.mapper.class_
        local_col, remote_col = _local_remote(rel)
        stmt = select(sqla_func.count()).where(remote_col == local_col)
        scope_where = _global_scope_whereclause(related_cls)
        if scope_where is not None:
            stmt = stmt.where(scope_where)
        return stmt.correlate(model).scalar_subquery()

    link = target.btm_link
    if link is None:
        raise UnknownRelationError(model.__name__, "?")
    pivot = link.table
    related_cls = link.related_model
    local_col = _primary_key_column(model)
    pivot_fk = pivot.c[link.foreign_key]
    pivot_rfk = pivot.c[link.related_foreign_key]
    remote_col = _primary_key_column(related_cls)
    scope_where = _global_scope_whereclause(related_cls)
    if scope_where is None:
        return (
            select(sqla_func.count())
            .select_from(pivot)
            .where(pivot_fk == local_col)
            .correlate(model)
            .scalar_subquery()
        )
    # Soft-deletable pivot target: join the related table so the scope can filter trashed rows.
    return (
        select(sqla_func.count())
        .select_from(pivot.join(related_cls, pivot_rfk == remote_col))
        .where(pivot_fk == local_col)
        .where(scope_where)
        .correlate(model)
        .scalar_subquery()
    )


def _is_pk_tuple(pk: object) -> TypeGuard[tuple[Any, ...]]:
    return isinstance(pk, tuple)


def _coerce_pk_to_tuple(pk: object) -> tuple[Any, ...]:
    """Normalise a primary-key value into a tuple suitable for composite-PK joins."""
    if _is_pk_tuple(pk):
        return pk
    return (pk,)


# ── keyset pagination helpers ───────────────────────────────────────────────

_KeysetEntry = tuple[str, InstrumentedAttribute[Any], str]  # (col_name, attr, "asc"|"desc")


def _parse_keyset_columns(model: type[Any], keyset: list[str]) -> list[_KeysetEntry]:
    """Parse ``["published_at DESC", "id ASC"]`` into (name, attr, direction) triples."""
    entries: list[_KeysetEntry] = []
    for spec in keyset:
        parts = spec.strip().split()
        col_name = parts[0].lstrip("-")
        direction = (
            "desc"
            if (len(parts) > 1 and parts[1].upper() == "DESC") or spec.startswith("-")
            else "asc"
        )
        attr = _resolve_column(model, col_name)
        entries.append((col_name, attr, direction))
    return entries


def _apply_keyset_where(
    stmt: Any,
    parsed: list[_KeysetEntry],
    cursor_vals: dict[str, Any],
) -> Any:
    """Append a row-value WHERE clause for the composite keyset cursor.

    For a two-column keyset ``(published_at DESC, id ASC)`` the predicate is::

        WHERE (published_at < :v0 OR (published_at = :v0 AND id > :v1))

    This is equivalent to the SQL row-value syntax ``(a, b) < (:v0, :v1)``
    but expressed in Python to stay compatible with SQLAlchemy's parameter
    binding without raw text.
    """
    from sqlalchemy import and_, or_

    def _clause(index: int) -> Any:
        col_name, attr, direction = parsed[index]
        raw_val = cursor_vals[col_name]
        # Strings that look like ISO datetimes are cast back to datetime for
        # proper parameterised comparison without dialect-specific CAST.
        val: Any = _coerce_cursor_value(raw_val, attr)
        lt = attr < val if direction == "asc" else attr > val
        eq = attr == val
        if index + 1 == len(parsed):
            return lt
        return or_(lt, and_(eq, _clause(index + 1)))

    return stmt.where(_clause(0))


def _coerce_cursor_value(raw: Any, attr: InstrumentedAttribute[Any]) -> Any:
    """Best-effort coercion of a cursor value back to the column's Python type."""
    if not isinstance(raw, str):
        return raw
    # Try ISO datetime first.
    try:
        from datetime import datetime

        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    # Try UUID.
    try:
        import uuid

        return uuid.UUID(raw)
    except ValueError, AttributeError:
        pass
    return raw


class QueryBuilder(Generic[T]):
    """Generic fluent query builder.

    Chain methods return ``Self``; terminal methods return ``T``-typed values.
    Wraps a SQLAlchemy ``Select[Tuple[T]]`` and a small set of pending modifiers.
    """

    def __init__(self, model: type[T], stmt: Select[Any] | None = None) -> None:
        self._model = model
        self._stmt: Select[Any] = stmt if stmt is not None else select(model)
        self._removed_global_scopes: set[str] = set()
        self._remove_all_global_scopes: bool = False
        self._ctes: list[tuple[str, CTE]] = []
        self._lock_for_update: bool = False
        self._lock_shared: bool = False
        self._select_columns: list[Any] | None = None
        self._raw_select_expr: str | None = None  # for select_raw()

    @property
    def model(self) -> type[T]:
        """Return the model class this builder targets."""
        return self._model

    @property
    def statement(self) -> Select[Any]:
        """Return the underlying SQLAlchemy ``Select`` for this builder."""
        return self._stmt

    # ------------------------------------------------------------------ scope forwarding

    def __getattr__(self, name: str) -> Any:
        """Forward unknown method lookups to scope methods on the model.

        Two flavours are recognised:
          - explicit ``@scope``-decorated functions (carry ``__arvel_scope__``)
          - ``scope_<name>`` auto-discovery (Laravel-style; no decorator
            needed). Signature is ``(self, query, *args)``; the framework
            supplies ``cls.__new__(cls)`` as ``self``.
        """
        for klass in self._model.__mro__:
            val = vars(klass).get(name)
            if val is not None and getattr(val, "__arvel_scope__", False):
                fn = getattr(val, "_fn", val)
                return partial(fn, self)

        scope_attr = f"scope_{name}"
        for klass in self._model.__mro__:
            raw = vars(klass).get(scope_attr)
            if raw is None:
                continue
            from arvel.database.model import unwrap_method

            fn = unwrap_method(raw)
            if isinstance(raw, staticmethod):
                return partial(fn, self)
            if isinstance(raw, classmethod):
                return partial(fn, self._model, self)
            instance = object.__new__(self._model)
            return partial(fn, instance, self)

        raise AttributeError(f"'{self._model.__name__}' query has no scope or attribute '{name}'")

    # ------------------------------------------------------------------ chain

    def _clone(self, stmt: Select[Any] | None = None) -> Self:
        new = type(self)(self._model, stmt if stmt is not None else self._stmt)
        new._removed_global_scopes = set(self._removed_global_scopes)
        new._remove_all_global_scopes = self._remove_all_global_scopes
        new._ctes = list(self._ctes)
        new._lock_for_update = self._lock_for_update
        new._lock_shared = self._lock_shared
        new._select_columns = list(self._select_columns) if self._select_columns else None
        new._raw_select_expr = self._raw_select_expr
        return new

    def where(self, *clauses: Any, **kwargs: Any) -> Self:
        stmt = self._stmt
        for clause in clauses:
            stmt = stmt.where(clause)
        for key, value in kwargs.items():
            col = _resolve_column(self._model, key)
            stmt = stmt.where(col == value)
        return self._clone(stmt)

    def or_where(self, *clauses: Any, **kwargs: Any) -> Self:
        from sqlalchemy import or_

        terms: list[Any] = list(clauses)
        for key, value in kwargs.items():
            col = _resolve_column(self._model, key)
            terms.append(col == value)
        if not terms:
            return self._clone()
        stmt = self._stmt.where(or_(*terms))
        return self._clone(stmt)

    def where_in(self, col: Any, values: Iterable[Any]) -> Self:
        column = _resolve_column(self._model, col)
        return self._clone(self._stmt.where(column.in_(list(values))))

    def where_not_in(self, col: Any, values: Iterable[Any]) -> Self:
        column = _resolve_column(self._model, col)
        return self._clone(self._stmt.where(~column.in_(list(values))))

    def where_between(self, col: Any, low: Any, high: Any) -> Self:
        column = _resolve_column(self._model, col)
        return self._clone(self._stmt.where(column.between(low, high)))

    def where_not_between(self, col: Any, low: Any, high: Any) -> Self:
        column = _resolve_column(self._model, col)
        return self._clone(self._stmt.where(~column.between(low, high)))

    def where_null(self, col: Any) -> Self:
        column = _resolve_column(self._model, col)
        return self._clone(self._stmt.where(column.is_(None)))

    def where_not_null(self, col: Any) -> Self:
        column = _resolve_column(self._model, col)
        return self._clone(self._stmt.where(column.is_not(None)))

    def where_raw(self, raw_sql: str, bindings: dict[str, Any] | None = None) -> Self:
        clause = text(raw_sql).bindparams(**(bindings or {}))
        return self._clone(self._stmt.where(clause))

    def where_column(self, col1: str, col2: str) -> Self:
        c1 = _resolve_column(self._model, col1)
        c2 = _resolve_column(self._model, col2)
        return self._clone(self._stmt.where(c1 == c2))

    def where_exists(self, subquery_fn: Callable[[QueryBuilder[T]], Any]) -> Self:
        from sqlalchemy import exists as sqla_exists

        sub = subquery_fn(type(self)(self._model))
        sub_stmt = sub.apply_global_scopes() if hasattr(sub, "apply_global_scopes") else sub
        return self._clone(self._stmt.where(sqla_exists(sub_stmt)))

    def where_any(self, columns: list[str], operator: str, value: Any) -> Self:
        from sqlalchemy import or_

        if operator not in _WHERE_ANY_OPS:
            raise ValueError(
                f"where_any() received unsupported operator {operator!r}. "
                f"Valid operators: {sorted(_WHERE_ANY_OPS)}"
            )
        parts = [_apply_operator(_resolve_column(self._model, c), operator, value) for c in columns]
        if not parts:
            return self._clone()
        return self._clone(self._stmt.where(or_(*parts)))

    def where_json_path(
        self,
        column: str | InstrumentedAttribute[Any],
        path: str,
        value: Any,
    ) -> Self:
        """Filter on a JSONB column path using PostgreSQL's ``->>`` operator.

        Emits ``column->>'path' = :value``. PostgreSQL-only; ``path`` must be a
        string key (not a nested dot-path — use ``where_raw`` for those).
        Both ``column`` and ``path`` are developer-supplied identifiers, not
        user input, so interpolation into the SQL template is safe.

        Example::

            Product.where_json_path("slug", "en", slug_value)
            # → WHERE slug->>'en' = :__json_path_val__
        """
        col_name: str = column if isinstance(column, str) else column.key
        sql = text(f"{col_name}->>'{path}' = :__json_path_val__").bindparams(
            __json_path_val__=value
        )
        return self._clone(self._stmt.where(sql))

    def where_json_contains(
        self,
        column: str | InstrumentedAttribute[Any],
        value: Any,
    ) -> Self:
        """Filter on PostgreSQL JSONB containment using ``@>``."""
        from sqlalchemy import String, bindparam

        col_name: str = column if isinstance(column, str) else column.key
        payload = json.dumps(value)
        sql = text(f"{col_name} @> CAST(:__json_contains_val__ AS jsonb)").bindparams(
            bindparam("__json_contains_val__", payload, type_=String())
        )
        return self._clone(self._stmt.where(sql))

    def when(
        self,
        condition: Any,
        callback: Callable[[Self], Self],
        otherwise: Callable[[Self], Self] | None = None,
    ) -> Self:
        if condition:
            return callback(self._clone())
        if otherwise is not None:
            return otherwise(self._clone())
        return self._clone()

    def order_by(self, *cols: Any) -> Self:
        resolved: list[Any] = []
        for c in cols:
            if isinstance(c, str) and c.startswith("-"):
                resolved.append(desc(_resolve_column(self._model, c[1:])))
            elif isinstance(c, str):
                resolved.append(_resolve_column(self._model, c))
            else:
                resolved.append(c)
        return self._clone(self._stmt.order_by(*resolved))

    def order_by_raw(self, raw_sql: str) -> Self:
        return self._clone(self._stmt.order_by(text(raw_sql)))

    def where_full_text(
        self,
        col: InstrumentedAttribute[Any],
        query: str,
        *,
        tsquery_fn: str = "plainto_tsquery",
        lang: str = "english",
    ) -> Self:
        """Filter by PostgreSQL full-text search using the @@ operator.

        tsquery_fn must be one of the four standard PostgreSQL tsquery constructors.
        query is always a bind parameter — never interpolated into the SQL string.
        """
        if tsquery_fn not in _TSQUERY_FNS:
            raise ValueError(
                f"tsquery_fn must be one of {sorted(_TSQUERY_FNS)!r}, got {tsquery_fn!r}"
            )
        from sqlalchemy import literal

        tsq = getattr(func, tsquery_fn)(sqla_cast(literal(lang), REGCONFIG), query)
        clause = col.op("@@")(tsq)
        return self._clone(self._stmt.where(clause))

    def order_by_relevance(
        self,
        col: InstrumentedAttribute[Any],
        query: str,
        *,
        lang: str = "english",
    ) -> Self:
        """Order by PostgreSQL ts_rank descending — ranks FTS results by relevance."""
        from sqlalchemy import literal

        tsq = func.plainto_tsquery(sqla_cast(literal(lang), REGCONFIG), query)
        rank_expr = func.ts_rank(col, tsq).desc()
        return self._clone(self._stmt.order_by(rank_expr))

    def latest(self, col: str = "created_at") -> Self:
        column = _resolve_column(self._model, col)
        return self._clone(self._stmt.order_by(column.desc()))

    def oldest(self, col: str = "created_at") -> Self:
        column = _resolve_column(self._model, col)
        return self._clone(self._stmt.order_by(column.asc()))

    def limit(self, n: int) -> Self:
        return self._clone(self._stmt.limit(n))

    def offset(self, n: int) -> Self:
        return self._clone(self._stmt.offset(n))

    def group_by(self, *cols: Any) -> Self:
        resolved = [_resolve_column(self._model, c) if isinstance(c, str) else c for c in cols]
        return self._clone(self._stmt.group_by(*resolved))

    def having(self, clause: Any) -> Self:
        return self._clone(self._stmt.having(clause))

    def having_raw(self, raw_sql: str, bindings: dict[str, Any] | None = None) -> Self:
        clause = text(raw_sql).bindparams(**(bindings or {}))
        return self._clone(self._stmt.having(clause))

    def distinct(self, *cols: Any) -> Self:
        return self._clone(self._stmt.distinct(*cols))

    def select(self, *columns: str) -> Self:
        """Limit the SELECT to specific column names (or literal SQL like '1')."""
        cols: list[Any] = []
        for c in columns:
            try:
                cols.append(_resolve_column(self._model, c))
            except AttributeError:
                cols.append(text(c))
        new = self._clone(self._stmt.with_only_columns(*cols, maintain_column_froms=True))
        new._select_columns = ["__cols__"]
        return new

    def select_raw(self, raw_sql: str) -> Self:
        """Replace the SELECT list with a raw SQL expression, preserving the FROM clause."""
        new = self._clone()
        new._select_columns = ["__raw__"]
        # Store the raw SELECT expression separately — used in all()
        object.__setattr__(new, "_raw_select_expr", raw_sql)
        return new

    def join(self, target: type[Any], *clauses: Any, **kwargs: Any) -> Self:
        return self._clone(self._stmt.join(target, *clauses, **kwargs))

    def left_join(self, target: type[Any], *clauses: Any, **kwargs: Any) -> Self:
        return self._clone(self._stmt.outerjoin(target, *clauses, **kwargs))

    def with_(
        self,
        *relations: str | Mapping[str, Callable[[QueryBuilder[Any]], QueryBuilder[Any]]],
    ) -> Self:
        stmt = self._stmt
        for item in relations:
            if isinstance(item, Mapping):
                for path, callback in item.items():
                    stmt = stmt.options(
                        _selectin_loader_for_path(self._model, path, constraint=callback)
                    )
            elif type(item) is str:
                stmt = stmt.options(_selectin_loader_for_path(self._model, item))
            else:
                raise TypeError(
                    f"{self._model.__name__}.with_() expects str relation paths or "
                    f"dict[str, callback] mappings, got {type(item).__name__}."
                )
        return self._clone(stmt)

    def with_count(self, *relations: str) -> Self:
        """Add {relation}_count columns via correlated COUNT subqueries.

        Honours the related model's soft-delete scope and supports belongs-to-many.
        Raises UnknownRelationError for relations the model doesn't define.
        """
        stmt = self._stmt
        for rel_name in relations:
            target = _resolve_relation(self._model, rel_name)
            count_sub = _count_subquery(self._model, target).label(f"{rel_name}_count")
            stmt = stmt.add_columns(count_sub)
        clone = self._clone()
        clone._stmt = stmt
        clone._select_columns = ["__with_count__"]
        return clone

    def with_sum(self, relation: str, col: str) -> Self:
        """Add {relation}_sum_{col} column via correlated SUM subquery."""
        from sqlalchemy import func as sqla_func

        stmt = self._stmt
        mapper = _mapper_of(self._model)
        rel = mapper.relationships.get(relation)
        if rel is not None:
            local_col, remote_col = _local_remote(rel)
            sum_col = getattr(rel.mapper.class_, col)
            sum_sub = (
                select(sqla_func.sum(sum_col))
                .where(remote_col == local_col)
                .correlate(self._model)
                .scalar_subquery()
                .label(f"{relation}_sum_{col}")
            )
            stmt = stmt.add_columns(sum_sub)
        clone = self._clone()
        clone._stmt = stmt
        clone._select_columns = ["__with_agg__"]
        return clone

    def with_max(self, relation: str, col: str) -> Self:
        from sqlalchemy import func as sqla_func

        stmt = self._stmt
        mapper = _mapper_of(self._model)
        rel = mapper.relationships.get(relation)
        if rel is not None:
            local_col, remote_col = _local_remote(rel)
            agg_col = getattr(rel.mapper.class_, col)
            max_sub = (
                select(sqla_func.max(agg_col))
                .where(remote_col == local_col)
                .correlate(self._model)
                .scalar_subquery()
                .label(f"{relation}_max_{col}")
            )
            stmt = stmt.add_columns(max_sub)
        clone = self._clone()
        clone._stmt = stmt
        clone._select_columns = ["__with_agg__"]
        return clone

    def where_has(
        self,
        relation: str | Any,
        constraint: Callable[[QueryBuilder[Any]], QueryBuilder[Any]] | None = None,
    ) -> Self:
        """Filter to rows that have at least one matching related row."""
        from sqlalchemy import exists as sqla_exists

        target = _resolve_relation(self._model, relation)
        sub = _exists_subquery(self._model, target, constraint)
        return self._clone(self._stmt.where(sqla_exists(sub)))

    def doesnt_have(self, relation: str | Any) -> Self:
        from sqlalchemy import exists as sqla_exists

        target = _resolve_relation(self._model, relation)
        sub = _exists_subquery(self._model, target)
        return self._clone(self._stmt.where(~sqla_exists(sub)))

    def has(self, relation: str | Any, operator: str = ">=", count: int = 1) -> Self:
        target = _resolve_relation(self._model, relation)
        cnt_sub = _count_subquery(self._model, target)
        op_map = {
            ">=": cnt_sub >= count,
            ">": cnt_sub > count,
            "<=": cnt_sub <= count,
            "<": cnt_sub < count,
            "=": cnt_sub == count,
            "!=": cnt_sub != count,
        }
        cond = op_map.get(operator, cnt_sub >= count)
        return self._clone(self._stmt.where(cond))

    def where_pivot(self, column: str, value: Any) -> Self:
        """Filter via pivot table column — only valid on BelongsToManyAccessor.

        On a regular QueryBuilder, raises RuntimeError (table not set).
        """
        raise RuntimeError(
            "where_pivot() is only available on BelongsToManyAccessor, not on a plain QueryBuilder."
        )

    def without_global_scope(self, name: str) -> Self:
        new = self._clone()
        new._removed_global_scopes.add(name)
        return new

    def without_global_scopes(self) -> Self:
        new = self._clone()
        new._remove_all_global_scopes = True
        return new

    def with_trashed(self) -> Self:
        """Include soft-deleted rows in results."""
        if not getattr(self._model, "__arvel_soft_delete_column__", None):
            raise AttributeError(
                f"{self._model.__name__} does not use SoftDeletes — with_trashed() unavailable."
            )
        return self.without_global_scope("soft_delete")

    def only_trashed(self) -> Self:
        """Return only soft-deleted rows."""
        col_name = getattr(self._model, "__arvel_soft_delete_column__", None)
        if not col_name:
            raise AttributeError(
                f"{self._model.__name__} does not use SoftDeletes — only_trashed() unavailable."
            )
        col = getattr(self._model, col_name)
        return self.without_global_scope("soft_delete").where(col.is_not(None))

    def lock_for_update(self) -> Self:
        clone = self._clone()
        clone._lock_for_update = True
        clone._lock_shared = False
        return clone

    def lock(self) -> Self:
        """Alias for lock_for_update() — mirrors Laravel's shorter form."""
        return self.lock_for_update()

    def shared_lock(self) -> Self:
        """Emit SELECT ... FOR SHARE (advisory read lock; other readers can proceed)."""
        clone = self._clone()
        clone._lock_shared = True
        clone._lock_for_update = False
        return clone

    def union(self, other: QueryBuilder[Any]) -> Self:
        """UNION (deduplicates rows)."""
        combined = self.apply_global_scopes().union(other.apply_global_scopes())
        # ``Select.from_statement`` is typed by SQLAlchemy as the more general
        # ``ExecutableReturnsRows``; at runtime it returns the originating
        # ``Select`` instance, which is what ``_clone`` consumes.
        return self._clone(cast("Select[Any]", select(self._model).from_statement(combined)))

    def union_all(self, other: QueryBuilder[Any]) -> Self:
        """UNION ALL (keeps duplicates)."""
        combined = self.apply_global_scopes().union_all(other.apply_global_scopes())
        return self._clone(cast("Select[Any]", select(self._model).from_statement(combined)))

    # ------------------------------------------------------------------ apply scopes

    def apply_global_scopes(self) -> Select[Any]:
        if self._remove_all_global_scopes:
            stmt = self._stmt
        else:
            scopes: dict[str, Callable[[QueryBuilder[Any]], QueryBuilder[Any]]] = getattr(
                self._model, "__arvel_global_scopes__", {}
            )
            if not scopes:
                stmt = self._stmt
            else:
                current_qb: QueryBuilder[Any] = self
                for name, scope_fn in scopes.items():
                    if name in self._removed_global_scopes:
                        continue
                    current_qb = scope_fn(current_qb)
                stmt = current_qb._stmt

        for _name, cte in self._ctes:
            stmt = stmt.add_cte(cte)
        return stmt

    # ------------------------------------------------------------------ CTE / recursive

    def with_cte(self, name: str, cte: CTE) -> Self:
        clone = self._clone()
        clone._ctes.append((name, cte))
        return clone

    def recursive(
        self,
        parent_key: str,
        *,
        id_key: str = "id",
        depth_col: str | None = None,
        path_col: str | None = None,
    ) -> RecursiveQueryBuilder[T]:
        rb: RecursiveQueryBuilder[T] = RecursiveQueryBuilder(
            self._model,
            self._stmt,
            parent_key=parent_key,
            id_key=id_key,
            depth_col=depth_col,
            path_col=path_col,
        )
        rb._removed_global_scopes = set(self._removed_global_scopes)
        rb._remove_all_global_scopes = self._remove_all_global_scopes
        rb._ctes = list(self._ctes)
        return rb

    # ------------------------------------------------------------------ SQL inspection

    def _apply_locks(self, stmt: Select[Any]) -> Select[Any]:
        if self._lock_for_update:
            return stmt.with_for_update()
        if self._lock_shared:
            return stmt.with_for_update(read=True)
        return stmt

    def to_sql(self, *, dialect: str | None = None) -> str:
        stmt = self._apply_locks(self.apply_global_scopes())
        sqla_dialect = _resolve_sqla_dialect(dialect)
        try:
            compiled = stmt.compile(
                dialect=sqla_dialect,
                compile_kwargs={"literal_binds": True},
            )
        except Exception as exc:
            from arvel.database.exceptions import QueryCompileError

            raise QueryCompileError(str(exc)) from exc
        return str(compiled)

    # --------------------------------------------------------------- raw select helper

    async def _execute_raw_select(self) -> list[dict[str, Any]]:
        """Execute a ``select_raw()`` query.

        Splits the user-supplied SELECT list on top-level commas and feeds each
        expression to :func:`sqlalchemy.literal_column` so SQLAlchemy can size
        the result mapping correctly. WHERE / GROUP BY / HAVING / ORDER / LIMIT
        keep using SQLAlchemy's bind-parameter pipeline — no manual SQL string
        splicing. ``select_raw`` is, by name, an opt-in escape hatch for trusted
        SQL fragments; the caller owns sanitization of those fragments.
        """
        from sqlalchemy import literal_column

        raw_expr: str = self._raw_select_expr or "*"
        cols: list[Any] = [literal_column(part) for part in _split_select_list(raw_expr)] or [
            literal_column("*")
        ]
        scoped_stmt = self.apply_global_scopes()
        raw_stmt: Select[Any] = scoped_stmt.with_only_columns(
            *cols,
            maintain_column_froms=True,
        )
        session = get_active_session()
        result = await session.execute(raw_stmt)
        keys = list(result.keys())
        return [dict(zip(keys, row, strict=False)) for row in result.all()]

    # === terminal (read) ============================================================

    async def first(self) -> T | None:
        stmt = self.apply_global_scopes().limit(1)
        if self._lock_for_update:
            stmt = stmt.with_for_update()
        elif self._lock_shared:
            stmt = stmt.with_for_update(read=True)
        result = await get_active_session().execute(stmt)
        return cast("T | None", result.scalars().first())

    async def first_or_fail(self) -> T:
        instance = await self.first()
        if instance is None:
            raise ModelNotFoundError(self._model.__name__, "first()")
        return instance

    async def first_or(self, callback: Callable[[], T]) -> T:
        instance = await self.first()
        return instance if instance is not None else callback()

    async def first_or_create(
        self, attributes: dict[str, Any], values: dict[str, Any] | None = None
    ) -> T:
        """Return the first row matching *attributes*, or create it with *attributes* + *values*."""
        instance = await self.where(**attributes).first()
        if instance is not None:
            return instance
        model_factory = cast("_ModelFactory", self._model)
        return cast("T", await model_factory.create(**{**attributes, **(values or {})}))

    async def first_or_new(
        self, attributes: dict[str, Any], values: dict[str, Any] | None = None
    ) -> T:
        """Return the first row matching *attributes*, or an unsaved instance built from both."""
        instance = await self.where(**attributes).first()
        if instance is not None:
            return instance
        return cast("T", cast("Any", self._model)(**{**attributes, **(values or {})}))

    async def update_or_create(self, attributes: dict[str, Any], values: dict[str, Any]) -> T:
        """Update the first row matching attributes, or create it."""
        instance = await self.where(**attributes).first()
        if instance is None:
            model_factory = cast("_ModelFactory", self._model)
            return cast("T", await model_factory.create(**{**attributes, **values}))

        fill = getattr(instance, "fill", None)
        if callable(fill):
            fill(**values)
        else:
            for key, value in values.items():
                setattr(instance, key, value)
        saveable = cast("_SaveableModel", instance)
        await saveable.save()
        return instance

    async def sole(self) -> T:
        """Return exactly one row. Raises if zero or more than one row matches."""
        stmt = self.apply_global_scopes()
        if self._lock_for_update:
            stmt = stmt.with_for_update()
        elif self._lock_shared:
            stmt = stmt.with_for_update(read=True)
        result = await get_active_session().execute(stmt)
        rows = list(result.scalars().all())
        if len(rows) == 0:
            raise ModelNotFoundError(self._model.__name__, "sole()")
        if len(rows) > 1:
            raise MultipleResultsError(self._model.__name__)
        return cast("T", rows[0])

    async def find(self, pk: Any) -> T | None:
        # Route through the scoped QB so global scopes (soft-delete, tenant, etc.) apply.
        # session.get() is an identity-map lookup that bypasses all query scopes.
        mapper: Mapper[Any] = cast("Mapper[Any]", sqla_inspect(self._model))
        pk_cols = mapper.primary_key
        if len(pk_cols) == 1:
            col_key = pk_cols[0].key
            if col_key is None:
                raise TypeError("Primary key column has no key")
            pk_attr = getattr(self._model, col_key)
            return await self._clone(self._stmt).where(pk_attr == pk).first()
        qb = self._clone(self._stmt)
        pk_values = _coerce_pk_to_tuple(pk)
        for col, val in zip(pk_cols, pk_values, strict=False):
            if col.key is None:
                raise TypeError("Primary key column has no key")
            qb = qb.where(getattr(self._model, col.key) == val)
        return await qb.first()

    async def find_or_fail(self, pk: Any) -> T:
        instance = await self.find(pk)
        if instance is None:
            raise ModelNotFoundError(self._model.__name__, pk)
        return instance

    async def all(self) -> Any:
        from arvel.support.collections import Collection

        stmt = self.apply_global_scopes()
        if self._lock_for_update:
            stmt = stmt.with_for_update()
        elif self._lock_shared:
            stmt = stmt.with_for_update(read=True)

        # select_raw() → build a full raw SQL query
        if self._select_columns and self._select_columns[0] == "__raw__" and self._raw_select_expr:
            raw_result = await self._execute_raw_select()
            return Collection(raw_result)

        # select() with specific column names → return dicts
        if self._select_columns and self._select_columns[0] == "__cols__":
            result = await get_active_session().execute(stmt)
            return Collection(dict(row) for row in result.mappings().all())

        # with_count/with_sum/with_max columns were added — rows are Row tuples
        if self._select_columns and self._select_columns[0] in (
            "__with_count__",
            "__with_agg__",
        ):
            result = await get_active_session().execute(stmt)
            column_keys: list[Any] = list(result.keys())
            rows = result.all()
            items: list[T] = []
            for row in rows:
                obj = row[0]
                # Attach with_count / with_sum / with_max scalar columns onto
                # the loaded instance using the result's column-name keys.
                # Per-attribute failures (read-only descriptors, frozen
                # dataclasses) are isolated with suppress().
                row_seq: Sequence[Any] = row
                for i, key in enumerate(column_keys):
                    if isinstance(key, str):
                        with contextlib.suppress(AttributeError, TypeError):
                            object.__setattr__(obj, key, row_seq[i])
                items.append(cast("T", obj))
            return Collection(items)

        result = await get_active_session().execute(stmt)
        return Collection(result.scalars().all())

    async def get(self) -> Any:
        return await self.all()

    async def count(self) -> int:
        stmt = self.apply_global_scopes()
        count_stmt = select(func.count()).select_from(stmt.subquery())
        result = await get_active_session().execute(count_stmt)
        return int(result.scalar_one())

    async def exists(self) -> bool:
        return await self.count() > 0

    async def value(self, col: str) -> Any:
        column = _resolve_column(self._model, col)
        stmt = self.apply_global_scopes().with_only_columns(column).limit(1)
        result = await get_active_session().execute(stmt)
        return result.scalar()

    async def pluck(self, col: str) -> list[Any]:
        column = _resolve_column(self._model, col)
        stmt = self.apply_global_scopes().with_only_columns(column)
        result = await get_active_session().execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------ aggregates

    async def sum(self, col: str) -> Any:
        column = _resolve_column(self._model, col)
        stmt = self.apply_global_scopes().with_only_columns(func.sum(column))
        result = await get_active_session().execute(stmt)
        return result.scalar_one_or_none()

    async def avg(self, col: str) -> Any:
        column = _resolve_column(self._model, col)
        stmt = self.apply_global_scopes().with_only_columns(func.avg(column))
        result = await get_active_session().execute(stmt)
        return result.scalar_one_or_none()

    async def max(self, col: str) -> Any:
        column = _resolve_column(self._model, col)
        stmt = self.apply_global_scopes().with_only_columns(func.max(column))
        result = await get_active_session().execute(stmt)
        return result.scalar_one_or_none()

    async def min(self, col: str) -> Any:
        column = _resolve_column(self._model, col)
        stmt = self.apply_global_scopes().with_only_columns(func.min(column))
        result = await get_active_session().execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------ pagination

    async def paginate(self, per_page: int = 15, *, page: int = 1) -> Paginator[T]:
        total = await self.count()
        items_stmt = self.apply_global_scopes().limit(per_page).offset((page - 1) * per_page)
        result = await get_active_session().execute(items_stmt)
        from arvel.support.collections import Collection

        items: list[T] = cast("list[T]", Collection(result.scalars().all()))
        return Paginator(items=items, total=total, per_page=per_page, current_page=page)

    async def simple_paginate(self, per_page: int = 15, *, page: int = 1) -> SimplePaginator[T]:
        """No COUNT query — use for large tables or infinite scroll."""
        items_stmt = self.apply_global_scopes().limit(per_page + 1).offset((page - 1) * per_page)
        result = await get_active_session().execute(items_stmt)
        from arvel.support.collections import Collection

        rows: list[T] = cast("list[T]", list(result.scalars().all()))
        has_more = len(rows) > per_page
        return SimplePaginator(
            items=Collection(rows[:per_page]),
            per_page=per_page,
            current_page=page,
            has_more=has_more,
        )

    async def cursor_paginate(
        self,
        per_page: int = 15,
        *,
        cursor: str | None = None,
        keyset: list[str] | None = None,
    ) -> CursorPaginator[T]:
        """Cursor-based pagination with optional composite keyset support.

        ``keyset`` is a list of column-direction strings in the same format
        accepted by :meth:`order_by` (prefix ``-`` for descending)::

            await Product.query().cursor_paginate(
                per_page=20,
                cursor=request.query_params.get("cursor"),
                keyset=["published_at DESC", "id ASC"],
            )

        When ``keyset`` is omitted the method falls back to the legacy
        single-PK ascending cursor so existing callers are unaffected.

        Cursor tokens are opaque ``base64(json(values))`` strings.  The token
        encodes a dict mapping each keyset column to the last row's value so
        the next page starts **after** that position.

        The emitted WHERE clause uses a row-value comparison::

            WHERE (published_at, id) < (:cursor_0, :cursor_1)

        which PostgreSQL evaluates efficiently against a composite index.
        """
        if keyset:
            return await self._keyset_paginate(per_page, cursor=cursor, keyset=keyset)

        # Legacy single-PK path (backward-compatible).
        mapper = _mapper_of(self._model)
        pk_col = mapper.primary_key[0]
        pk_key = pk_col.key
        if pk_key is None:
            raise TypeError(f"{self._model.__name__} primary key column has no name.")
        pk_attr = _resolve_column(self._model, pk_key)

        stmt = self.apply_global_scopes().order_by(pk_attr)
        if cursor is not None:
            last_pk = json.loads(base64.b64decode(cursor.encode()).decode())
            stmt = stmt.where(pk_attr > last_pk)

        result = await get_active_session().execute(stmt.limit(per_page + 1))
        from arvel.support.collections import Collection

        rows: list[T] = cast("list[T]", list(result.scalars().all()))
        has_more = len(rows) > per_page
        items = Collection(rows[:per_page])
        next_cursor: str | None = None
        if has_more and items:
            last_pk_val = getattr(items[-1], pk_key)
            next_cursor = base64.b64encode(json.dumps(last_pk_val).encode()).decode()
        return CursorPaginator(items=items, per_page=per_page, next_cursor=next_cursor)

    async def _keyset_paginate(
        self,
        per_page: int,
        *,
        cursor: str | None,
        keyset: list[str],
    ) -> CursorPaginator[T]:
        """Composite keyset pagination implementation."""
        parsed = _parse_keyset_columns(self._model, keyset)
        col_names = [name for name, _, _ in parsed]

        # ORDER BY must match the keyset declaration.
        order_exprs = [desc(attr) if direction == "desc" else attr for _, attr, direction in parsed]
        stmt = self.apply_global_scopes().order_by(*order_exprs)

        if cursor is not None:
            try:
                cursor_vals: dict[str, Any] = json.loads(base64.b64decode(cursor.encode()).decode())
                stmt = _apply_keyset_where(stmt, parsed, cursor_vals)
            except ValueError, KeyError:
                pass  # Malformed cursor — ignore and return the first page.

        result = await get_active_session().execute(stmt.limit(per_page + 1))
        from arvel.support.collections import Collection

        rows: list[T] = cast("list[T]", list(result.scalars().all()))
        has_more = len(rows) > per_page
        items = Collection(rows[:per_page])
        next_cursor: str | None = None
        if has_more and items:
            last = items[-1]
            raw: dict[str, Any] = {}
            for col_name in col_names:
                val = getattr(last, col_name)
                if hasattr(val, "isoformat"):
                    raw[col_name] = val.isoformat()
                elif isinstance(val, _uuid.UUID):
                    raw[col_name] = str(val)
                else:
                    raw[col_name] = val
            next_cursor = base64.b64encode(json.dumps(raw).encode()).decode()
        return CursorPaginator(items=items, per_page=per_page, next_cursor=next_cursor)

    async def chunk(self, size: int, callback: Callable[[list[T]], Awaitable[None]]) -> None:
        page = 1
        while True:
            stmt = self.apply_global_scopes().limit(size).offset((page - 1) * size)
            result = await get_active_session().execute(stmt)
            batch: list[T] = cast("list[T]", list(result.scalars().all()))
            if not batch:
                return
            await callback(batch)
            if len(batch) < size:
                return
            page += 1

    async def each(self, callback: Callable[[T], Awaitable[None]]) -> None:
        async def _per_batch(batch: list[T]) -> None:
            for item in batch:
                await callback(item)

        await self.chunk(100, _per_batch)

    # === terminal (write) ===========================================================

    def _assert_writable(self, operation: str) -> None:
        """Raise ReadOnlyModelError when _model is a ViewModel."""
        if getattr(self._model, "__read_only__", False):
            from arvel.database.exceptions import ReadOnlyModelError

            raise ReadOnlyModelError(self._model.__name__, operation)

    async def insert(self, rows: list[dict[str, Any]]) -> None:
        self._assert_writable("insert")
        from sqlalchemy import insert as sqla_insert

        session = get_active_session()
        stmt = sqla_insert(_table_of(self._model)).values(rows)
        await session.execute(stmt)
        await session.flush()

    async def insert_get_id(self, row: dict[str, Any]) -> Any:
        self._assert_writable("insert_get_id")
        from sqlalchemy import insert as sqla_insert

        session = get_active_session()
        stmt = sqla_insert(_table_of(self._model)).values(**row)
        result = cast("CursorResult[Any]", await session.execute(stmt))
        await session.flush()
        return result.lastrowid

    async def update(self, values: dict[str, Any]) -> int:
        self._assert_writable("update")
        from sqlalchemy import update as sqla_update

        session = get_active_session()
        table = _table_of(self._model)
        stmt = sqla_update(table)
        where_clause = self.apply_global_scopes().whereclause
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        stmt = stmt.values(**values)
        result = cast("CursorResult[Any]", await session.execute(stmt))
        await session.flush()
        return result.rowcount

    async def update_or_insert(self, *, where: dict[str, Any], values: dict[str, Any]) -> None:
        """Update matching row or insert if absent."""
        self._assert_writable("update_or_insert")
        existing_count = await type(self)(self._model).where(**where).count()
        if existing_count > 0:
            await type(self)(self._model).where(**where).update(values)
        else:
            combined = {**where, **values}
            await self.insert([combined])

    async def upsert(
        self,
        rows: list[dict[str, Any]],
        *,
        unique_by: list[str],
        update: list[str],
    ) -> None:
        """INSERT … ON CONFLICT DO UPDATE — or manual check-and-upsert as fallback."""
        self._assert_writable("upsert")
        session = get_active_session()
        conn = await session.connection()
        dialect_name: str = conn.dialect.name

        # Check if unique_by columns have UNIQUE or PK constraints — required for
        # dialect-native ON CONFLICT. Fall back to manual if not.
        from sqlalchemy import UniqueConstraint

        table = _table_of(self._model)
        unique_cols: set[str] = {col.name for col in table.primary_key}
        for uc in table.constraints:
            if isinstance(uc, UniqueConstraint):
                for col in uc.columns:
                    unique_cols.add(col.name)

        has_constraint = all(c in unique_cols for c in unique_by)

        if has_constraint and dialect_name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            for row in rows:
                sqlite_stmt = sqlite_insert(table).values(**row)
                sqlite_stmt = sqlite_stmt.on_conflict_do_update(
                    index_elements=unique_by,
                    set_={k: getattr(sqlite_stmt.excluded, k) for k in update},
                )
                await session.execute(sqlite_stmt)
        elif has_constraint and dialect_name in ("postgresql", "postgres"):
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            for row in rows:
                pg_stmt = pg_insert(table).values(**row)
                pg_stmt = pg_stmt.on_conflict_do_update(
                    index_elements=unique_by,
                    set_={k: getattr(pg_stmt.excluded, k) for k in update},
                )
                await session.execute(pg_stmt)
        else:
            # Manual check-and-upsert for non-unique columns or unsupported dialects
            for row in rows:
                where_dict = {k: row[k] for k in unique_by if k in row}
                qb = type(self)(self._model).where(**where_dict)
                if await qb.count() > 0:
                    update_dict = {k: row[k] for k in update if k in row}
                    await qb.update(update_dict)
                else:
                    await type(self)(self._model).insert([row])
        await session.flush()

    async def increment(self, col: str, amount: int = 1) -> int:
        """Increment a column by ``amount`` and return the affected row count."""
        self._assert_writable("increment")
        from sqlalchemy import update as sqla_update

        session = get_active_session()
        table = _table_of(self._model)
        db_col = table.c[col]
        stmt = sqla_update(table).values({col: db_col + amount})
        where_clause = self.apply_global_scopes().whereclause
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        result = cast("CursorResult[Any]", await session.execute(stmt))
        await session.flush()
        return int(result.rowcount)

    async def decrement(self, col: str, amount: int = 1) -> int:
        """Decrement a column by ``amount`` and return the affected row count."""
        return await self.increment(col, -amount)

    async def delete(self) -> int:
        """Delete matching rows. Soft-deletes (UPDATE deleted_at) when the model
        uses SoftDeletes; otherwise issues a hard DELETE."""
        self._assert_writable("delete")
        soft_field: str | None = getattr(self._model, "__arvel_soft_delete_column__", None)
        if soft_field is not None:
            from datetime import UTC, datetime

            from sqlalchemy import update as sqla_update

            session = get_active_session()
            table = _table_of(self._model)
            stmt = sqla_update(table).values({soft_field: datetime.now(UTC)})
            where_clause = self.apply_global_scopes().whereclause
            if where_clause is not None:
                stmt = stmt.where(where_clause)
            result = cast("CursorResult[Any]", await session.execute(stmt))
            await session.flush()
            return int(result.rowcount)
        return await self._hard_delete()

    async def force_delete(self) -> int:
        """Permanently remove matching rows, including already-trashed ones."""
        self._assert_writable("force_delete")
        soft_field: str | None = getattr(self._model, "__arvel_soft_delete_column__", None)
        target = self.without_global_scope("soft_delete") if soft_field is not None else self
        return await target._hard_delete()

    async def _hard_delete(self) -> int:
        from sqlalchemy import delete as sqla_delete

        session = get_active_session()
        table = _table_of(self._model)
        stmt = sqla_delete(table)
        where_clause = self.apply_global_scopes().whereclause
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        result = cast("CursorResult[Any]", await session.execute(stmt))
        await session.flush()
        return int(result.rowcount)


class SimplePaginator(Generic[TItem]):
    """Paginator without a total count — suitable for large datasets."""

    def __init__(
        self,
        items: list[TItem],
        per_page: int,
        current_page: int,
        has_more: bool,
    ) -> None:
        self.items = items
        self.per_page = per_page
        self.current_page = current_page
        self.has_more = has_more
        self.total: int | None = None  # no count query

    def links(
        self,
        base_url: str,
        *,
        query: Mapping[str, str] | None = None,
    ) -> dict[str, str | None]:
        """Return ``{prev, next}`` URLs. No ``first``/``last`` — total is unknown."""
        from arvel.database.paginator import build_page_url

        prev_page = self.current_page - 1 if self.current_page > 1 else None
        next_page = self.current_page + 1 if self.has_more else None
        return {
            "prev": build_page_url(base_url, prev_page, query=query) if prev_page else None,
            "next": build_page_url(base_url, next_page, query=query) if next_page else None,
        }

    def to_dict(
        self,
        items_serializer: Callable[[TItem], Any] | None = None,
        *,
        base_url: str | None = None,
        query: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Return the paginator as ``{data, meta, links}``.

        ``meta.total`` is ``null`` — no count query was run.
        ``links`` values are integer page numbers unless ``base_url`` is set,
        in which case fully-built URL strings replace them.
        """
        data: list[Any] = (
            [items_serializer(item) for item in self.items]
            if items_serializer is not None
            else list(self.items)
        )
        if base_url is not None:
            links: dict[str, Any] = self.links(base_url, query=query)
        else:
            links = {
                "prev": self.current_page - 1 if self.current_page > 1 else None,
                "next": self.current_page + 1 if self.has_more else None,
            }
        return {
            "data": data,
            "meta": {
                "total": None,
                "per_page": self.per_page,
                "current_page": self.current_page,
            },
            "links": links,
        }


class CursorPaginator(Generic[TItem]):
    """Cursor-based paginator — opaque next_cursor for the next page."""

    def __init__(
        self,
        items: list[TItem],
        per_page: int,
        next_cursor: str | None,
    ) -> None:
        self.items = items
        self.per_page = per_page
        self.next_cursor = next_cursor

    @property
    def has_more(self) -> bool:
        return self.next_cursor is not None

    def to_dict(
        self,
        items_serializer: Callable[[TItem], Any] | None = None,
        *,
        base_url: str | None = None,
        query: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Return the paginator as ``{data, meta, links}``.

        Without ``base_url``, ``links.next`` is the raw opaque cursor token
        (or ``null`` on the last page). With ``base_url``, the cursor is
        composed into a URL — ``{base_url}?cursor={token}`` — merged with
        any ``query`` extras.
        """
        from arvel.database.paginator import build_cursor_url

        data: list[Any] = (
            [items_serializer(item) for item in self.items]
            if items_serializer is not None
            else list(self.items)
        )
        if base_url is not None and self.next_cursor is not None:
            next_link: str | None = build_cursor_url(base_url, self.next_cursor, query=query)
        elif base_url is not None:
            next_link = None
        else:
            next_link = self.next_cursor
        return {
            "data": data,
            "meta": {
                "per_page": self.per_page,
                "has_more": self.has_more,
            },
            "links": {
                "next": next_link,
            },
        }


class RecursiveQueryBuilder(QueryBuilder[T]):
    """QueryBuilder extended with recursive CTE execution and tree assembly."""

    def __init__(
        self,
        model: type[T],
        stmt: Select[Any] | None = None,
        *,
        parent_key: str = "parent_id",
        id_key: str = "id",
        depth_col: str | None = None,
        path_col: str | None = None,
    ) -> None:
        super().__init__(model, stmt)
        self._parent_key: str = parent_key
        self._id_key: str = id_key
        self._depth_col: str | None = depth_col
        self._path_col: str | None = path_col

    def _clone(self, stmt: Select[Any] | None = None) -> Self:
        new = cast("RecursiveQueryBuilder[T]", super()._clone(stmt))
        new._parent_key = self._parent_key
        new._id_key = self._id_key
        new._depth_col = self._depth_col
        new._path_col = self._path_col
        return cast("Self", new)

    def _build_id_depth_cte(self) -> tuple[Any, bool]:
        from sqlalchemy import literal

        model = self._model
        # B009: use a variable to avoid the "use attribute access" lint rule;
        # __tablename__ is guaranteed on every DeclarativeBase-derived model.
        _tbl_attr = "__tablename__"
        table_name: str = getattr(model, _tbl_attr)
        cte_name = f"{table_name}_tree"

        id_attr = _resolve_column(model, self._id_key)
        parent_attr = _resolve_column(model, self._parent_key)
        has_depth = self._depth_col is not None

        anchor_where_clauses = self.apply_global_scopes().whereclause

        if has_depth:
            anchor_select = select(
                id_attr.label(self._id_key),
                parent_attr.label(self._parent_key),
                literal(0).label("_tree_depth"),
            )
        else:
            anchor_select = select(
                id_attr.label(self._id_key),
                parent_attr.label(self._parent_key),
            )

        if anchor_where_clauses is not None:
            anchor_select = anchor_select.where(anchor_where_clauses)

        anchor_cte = anchor_select.cte(cte_name, recursive=True)

        if has_depth:
            recursive_select = select(
                id_attr.label(self._id_key),
                parent_attr.label(self._parent_key),
                (anchor_cte.c._tree_depth + 1).label("_tree_depth"),
            ).join(anchor_cte, parent_attr == anchor_cte.c[self._id_key])
        else:
            recursive_select = select(
                id_attr.label(self._id_key),
                parent_attr.label(self._parent_key),
            ).join(anchor_cte, parent_attr == anchor_cte.c[self._id_key])

        full_cte = anchor_cte.union_all(recursive_select)
        return full_cte, has_depth

    def _build_recursive_stmt(self) -> Select[Any]:
        full_cte, _ = self._build_id_depth_cte()
        return select(full_cte)

    def to_sql(self, *, dialect: str | None = None) -> str:
        stmt = self._build_recursive_stmt()
        sqla_dialect = _resolve_sqla_dialect(dialect)
        try:
            compiled = stmt.compile(
                dialect=sqla_dialect,
                compile_kwargs={"literal_binds": True},
            )
        except Exception as exc:
            from arvel.database.exceptions import QueryCompileError

            raise QueryCompileError(str(exc)) from exc
        return str(compiled)

    async def all(self) -> Any:
        from arvel.support.collections import Collection

        full_cte, has_depth = self._build_id_depth_cte()
        id_attr = _resolve_column(self._model, self._id_key)
        stmt = select(self._model).join(full_cte, id_attr == full_cte.c[self._id_key])
        if has_depth:
            stmt = stmt.order_by(full_cte.c._tree_depth)
        session = get_active_session()
        result = await session.execute(stmt)
        rows: list[T] = list(result.scalars().all())
        return Collection(rows)

    async def as_tree(self) -> list[TreeNode[T]]:
        from arvel.database.tree import TreeNode

        full_cte, has_depth = self._build_id_depth_cte()
        id_attr = _resolve_column(self._model, self._id_key)

        if has_depth:
            stmt = (
                select(self._model, full_cte.c._tree_depth)
                .join(full_cte, id_attr == full_cte.c[self._id_key])
                .order_by(full_cte.c._tree_depth)
            )
        else:
            stmt = select(self._model, func.literal(0).label("_tree_depth")).join(
                full_cte, id_attr == full_cte.c[self._id_key]
            )

        session = get_active_session()
        result = await session.execute(stmt)
        rows = result.all()

        id_key = self._id_key
        parent_key = self._parent_key

        nodes: dict[Any, TreeNode[T]] = {}
        ordered_pks: list[Any] = []

        for row in rows:
            obj = cast("T", row[0])
            depth = int(row[1])
            pk = getattr(obj, id_key)
            nodes[pk] = TreeNode(node=obj, depth=depth, children=[])
            ordered_pks.append(pk)

        roots: list[TreeNode[T]] = []
        for pk in ordered_pks:
            node = nodes[pk]
            obj = node.node
            parent_pk = getattr(obj, parent_key, None)
            if parent_pk is None or parent_pk not in nodes:
                roots.append(node)
            else:
                nodes[parent_pk].children.append(node)

        return roots


from arvel.database.tree import TreeNode  # noqa: E402

__all__ = ["CursorPaginator", "QueryBuilder", "RecursiveQueryBuilder", "SimplePaginator"]
