"""Typed fluent query builder."""

from __future__ import annotations

import base64
import binascii
import contextlib
import json
import uuid as _uuid
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, Generic, Protocol, Self, TypeGuard, TypeVar, cast

from sqlalchemy import (
    Select,
    String,
    Table,
    and_,
    desc,
    extract,
    func,
    or_,
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
from sqlalchemy.ext.associationproxy import AssociationProxy, AssociationProxyInstance
from sqlalchemy.orm import InstrumentedAttribute, Mapper, selectinload
from sqlalchemy.sql.elements import ColumnElement

from arvel.database.exceptions import (
    InvalidCursorError,
    ModelNotFoundError,
    MultipleResultsError,
    UnknownRelationError,
)
from arvel.database.orm._eager import set_eager_relation
from arvel.database.paginator import Paginator
from arvel.database.session import get_active_session

if TYPE_CHECKING:
    from sqlalchemy.sql.expression import CTE

    from arvel.database.orm.belongs_to_many import BelongsToManyLink
    from arvel.database.orm.morph_to_many import MorphToManyLink
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

_UNSET: Any = object()


class JoinOn:
    """Fluent ON-clause builder for joins — mirrors Laravel's ``JoinClause``.

    ``q.join_on(Other, lambda j: j.on(A.x == Other.y).or_on(A.z == Other.w))``
    """

    def __init__(self) -> None:
        self._predicate: Any = None

    def on(self, condition: Any) -> JoinOn:
        self._predicate = condition if self._predicate is None else and_(self._predicate, condition)
        return self

    def or_on(self, condition: Any) -> JoinOn:
        self._predicate = condition if self._predicate is None else or_(self._predicate, condition)
        return self

    def build(self) -> Any:
        return self._predicate


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
    """Resolved relation — a SQLAlchemy relationship, BelongsToMany, or MorphToMany."""

    kind: str
    sa_rel: Any | None = None
    btm_link: BelongsToManyLink | None = None
    mtm_link: MorphToManyLink | None = None


def _resolve_relation(model: type[Any], name: str | Any) -> _RelationTarget:
    if not isinstance(name, str):
        # Accept InstrumentedAttribute / QueryableAttribute — extract the key.
        name = name.key
    mapper = _mapper_of(model)
    rel = mapper.relationships.get(name)
    if rel is not None:
        return _RelationTarget(kind="sa", sa_rel=rel)

    from arvel.database.orm.belongs_to_many import BelongsToMany
    from arvel.database.orm.morph_to_many import MorphToMany

    descriptor = getattr(model, name, None)
    if isinstance(descriptor, BelongsToMany):
        return _RelationTarget(kind="btm", btm_link=descriptor.link_spec())
    if isinstance(descriptor, MorphToMany):
        return _RelationTarget(kind="mtm", mtm_link=descriptor.link_spec(model.__name__))

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
    elif target.kind == "mtm":
        mlink = target.mtm_link
        if mlink is None:
            raise UnknownRelationError(model.__name__, "?")
        pivot = mlink.table
        related_cls = mlink.related_model
        local_col = _primary_key_column(model)
        remote_col = _primary_key_column(related_cls)
        sub = (
            select(related_cls)
            .join(pivot, pivot.c[mlink.related_foreign_key] == remote_col)
            .where(pivot.c[mlink.id_column] == sqla_cast(local_col, String))
            .where(pivot.c[mlink.type_column] == mlink.owner_type)
        )
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


def _expand_association_proxy(
    model: type[Any], mapper: Mapper[Any], head: str, tail: str
) -> tuple[str, str]:
    """Rewrite an association-proxy head into its underlying ``link.value`` path.

    ``with_("roles")`` on a model whose ``roles`` is an ``association_proxy`` over
    ``role_assignments.role`` becomes ``role_assignments.role`` so the normal
    relationship loader can build the selectinload chain.
    """
    descriptor = mapper.all_orm_descriptors.get(head)
    if not isinstance(descriptor, AssociationProxy):
        return head, tail
    proxy = cast("AssociationProxyInstance[Any]", getattr(model, head))
    expanded = f"{proxy.target_collection}.{proxy.value_attr}"
    if tail:
        expanded = f"{expanded}.{tail}"
    new_head, _, new_tail = expanded.partition(".")
    return new_head, new_tail


def _selectin_loader_for_path(
    model: type[Any],
    relation_path: str,
    *,
    constraint: Callable[[QueryBuilder[Any]], QueryBuilder[Any]] | None = None,
) -> Any:
    """Build a selectinload option for *relation_path*, optionally filtered."""
    mapper = _mapper_of(model)
    head, _, tail = relation_path.partition(".")
    head, tail = _expand_association_proxy(model, mapper, head, tail)
    valid: set[str] = {r.key for r in mapper.relationships}
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

    if target.kind == "mtm":
        mlink = target.mtm_link
        if mlink is None:
            raise UnknownRelationError(model.__name__, "?")
        pivot = mlink.table
        related_cls = mlink.related_model
        local_col = _primary_key_column(model)
        remote_col = _primary_key_column(related_cls)
        pivot_rfk = pivot.c[mlink.related_foreign_key]
        scope_where = _global_scope_whereclause(related_cls)
        base = (
            select(sqla_func.count())
            .where(pivot.c[mlink.id_column] == sqla_cast(local_col, String))
            .where(pivot.c[mlink.type_column] == mlink.owner_type)
        )
        if scope_where is None:
            return base.select_from(pivot).correlate(model).scalar_subquery()
        return (
            base.select_from(pivot.join(related_cls, pivot_rfk == remote_col))
            .where(scope_where)
            .correlate(model)
            .scalar_subquery()
        )

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


@dataclass(frozen=True)
class _AsyncEagerSpec:
    """A pending batched eager-load for a MorphToMany/BelongsToMany path."""

    path: str
    constraint: Callable[[QueryBuilder[Any]], QueryBuilder[Any]] | None


def _is_async_relation(model: type[Any], path: str) -> bool:
    """True when *path*'s head is a MorphToMany/BelongsToMany descriptor."""
    head = path.partition(".")[0]
    try:
        target = _resolve_relation(model, head)
    except UnknownRelationError:
        return False
    return target.kind in ("btm", "mtm")


def _owner_pk_key(model: type[Any]) -> str:
    pk_key = _mapper_of(model).primary_key[0].key
    if pk_key is None:
        raise TypeError(f"{model.__name__} primary key column has no key")
    return pk_key


def _dedupe_by_pk(model: type[Any], objs: list[Any]) -> list[Any]:
    pk_key = _owner_pk_key(model)
    seen: set[Any] = set()
    out: list[Any] = []
    for obj in objs:
        key = getattr(obj, pk_key)
        if key not in seen:
            seen.add(key)
            out.append(obj)
    return out


async def _batch_load_async(
    model: type[Any],
    parents: list[Any],
    attr_name: str,
    target: _RelationTarget,
    constraint: Callable[[QueryBuilder[Any]], QueryBuilder[Any]] | None,
) -> list[Any]:
    """Load one pivot relation for every parent in a single query.

    Mirrors Eloquent's ``BelongsToMany::match``/``buildDictionary``: one
    ``WHERE pivot.owner_key IN (...)`` (plus ``morph_type`` for MorphToMany),
    then group the related rows by owner key and stash each parent's slice.
    """
    owner_pk_key = _owner_pk_key(model)
    owner_values = [getattr(p, owner_pk_key) for p in parents]
    owner_label = "__arvel_owner_key__"

    if target.kind == "mtm":
        mlink = target.mtm_link
        if mlink is None:
            raise UnknownRelationError(model.__name__, attr_name)
        related_cls = mlink.related_model
        owner_col = mlink.table.c[mlink.id_column]
        stmt = (
            select(related_cls, owner_col.label(owner_label))
            .join(
                mlink.table,
                mlink.table.c[mlink.related_foreign_key] == _primary_key_column(related_cls),
            )
            .where(mlink.table.c[mlink.type_column] == mlink.owner_type)
            .where(owner_col.in_({str(v) for v in owner_values}))
        )
    else:
        link = target.btm_link
        if link is None:
            raise UnknownRelationError(model.__name__, attr_name)
        related_cls = link.related_model
        owner_col = link.table.c[link.foreign_key]
        stmt = (
            select(related_cls, owner_col.label(owner_label))
            .join(
                link.table,
                link.table.c[link.related_foreign_key] == _primary_key_column(related_cls),
            )
            .where(owner_col.in_(set(owner_values)))
        )

    # No global-scope filter here: the cache must be a transparent substitute
    # for the lazy accessor, which also reads through the raw pivot join.
    if constraint is not None:
        sub_qb: QueryBuilder[Any] = QueryBuilder(related_cls, select(related_cls))
        sub_qb = constraint(sub_qb)
        where_clause = sub_qb.statement.whereclause
        if where_clause is not None:
            stmt = stmt.where(where_clause)

    result = await get_active_session().execute(stmt)
    grouped: dict[str, list[Any]] = {}
    for row in result.all():
        grouped.setdefault(str(row[1]), []).append(row[0])

    flat: list[Any] = []
    for parent in parents:
        related = grouped.get(str(getattr(parent, owner_pk_key)), [])
        set_eager_relation(parent, attr_name, related)
        flat.extend(related)
    return _dedupe_by_pk(related_cls, flat)


async def _load_async_relation_path(
    model: type[Any],
    parents: list[Any],
    path: str,
    constraint: Callable[[QueryBuilder[Any]], QueryBuilder[Any]] | None,
) -> None:
    """Batch-load *path* (optionally nested, e.g. ``roles.permissions``)."""
    head, _, tail = path.partition(".")
    target = _resolve_relation(model, head)
    if target.kind not in ("btm", "mtm"):
        raise UnknownRelationError(model.__name__, head)
    # A constraint closure applies to the leaf relation, as in Eloquent.
    related = await _batch_load_async(model, parents, head, target, None if tail else constraint)
    if not tail or not related:
        return
    link = target.mtm_link or target.btm_link
    if link is None:
        return
    await _load_async_relation_path(link.related_model, related, tail, constraint)


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
        # ASC walks forward with values greater than the cursor; DESC walks
        # forward with values smaller than it.
        boundary = attr > val if direction == "asc" else attr < val
        eq = attr == val
        if index + 1 == len(parsed):
            return boundary
        return or_(boundary, and_(eq, _clause(index + 1)))

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
        self._async_eager: list[_AsyncEagerSpec] = []
        # WHERE lives here, not on _stmt, so or_where can OR onto the whole chain.
        self._where_predicate: ColumnElement[bool] | None = None

    @property
    def model(self) -> type[T]:
        """Return the model class this builder targets."""
        return self._model

    @property
    def statement(self) -> Select[Any]:
        """Return the underlying SQLAlchemy ``Select``, with accumulated WHERE applied."""
        if self._where_predicate is None:
            return self._stmt
        return self._stmt.where(self._where_predicate)

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
        new._async_eager = list(self._async_eager)
        new._where_predicate = self._where_predicate
        return new

    def _with_predicate(self, predicate: ColumnElement[bool]) -> Self:
        new = self._clone()
        new._where_predicate = predicate
        return new

    def _and(self, condition: Any) -> Self:
        """AND ``condition`` onto the accumulated WHERE."""
        if self._where_predicate is None:
            return self._with_predicate(condition)
        return self._with_predicate(and_(self._where_predicate, condition))

    def _or(self, condition: Any) -> Self:
        """OR ``condition`` onto the accumulated WHERE (the whole chain, not just the last term)."""
        if self._where_predicate is None:
            return self._with_predicate(condition)
        return self._with_predicate(or_(self._where_predicate, condition))

    def _grouped_whereclause(self, callback: Callable[[Self], object]) -> Any:
        """Run a group callback on a fresh sub-builder and return its combined predicate.

        The callback must return a builder — Arvel builders are immutable, so a
        mutate-in-place closure (Laravel's style) would silently drop the group.
        Returns ``None`` when the callback added no clauses.
        """
        sub = type(self)(self._model)
        result = callback(sub)
        if not isinstance(result, QueryBuilder):
            raise TypeError(
                "where()/or_where() group callback must return the query builder, "
                "e.g. `lambda q: q.where(...).or_where(...)`."
            )
        return result._where_predicate

    def where(self, *clauses: Any, **kwargs: Any) -> Self:
        qb = self
        for clause in clauses:
            if callable(clause):
                group = self._grouped_whereclause(clause)
                if group is not None:
                    qb = qb._and(group)
            else:
                qb = qb._and(clause)
        for key, value in kwargs.items():
            qb = qb._and(_resolve_column(self._model, key) == value)
        return qb if qb is not self else self._clone()

    def _or_terms(self, clauses: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        """Combine positional clauses + kwargs into one OR-group predicate (or None)."""
        terms: list[Any] = []
        for clause in clauses:
            if callable(clause):
                group = self._grouped_whereclause(clause)
                if group is not None:
                    terms.append(group)
            else:
                terms.append(clause)
        for key, value in kwargs.items():
            terms.append(_resolve_column(self._model, key) == value)
        if not terms:
            return None
        return terms[0] if len(terms) == 1 else or_(*terms)

    def or_where(self, *clauses: Any, **kwargs: Any) -> Self:
        combined = self._or_terms(clauses, kwargs)
        if combined is None:
            return self._clone()
        return self._or(combined)

    def where_in(self, col: Any, values: Iterable[Any]) -> Self:
        column = _resolve_column(self._model, col)
        return self._and(column.in_(list(values)))

    def or_where_in(self, col: Any, values: Iterable[Any]) -> Self:
        column = _resolve_column(self._model, col)
        return self._or(column.in_(list(values)))

    def where_not_in(self, col: Any, values: Iterable[Any]) -> Self:
        column = _resolve_column(self._model, col)
        return self._and(~column.in_(list(values)))

    def or_where_not_in(self, col: Any, values: Iterable[Any]) -> Self:
        column = _resolve_column(self._model, col)
        return self._or(~column.in_(list(values)))

    def where_between(self, col: Any, low: Any, high: Any) -> Self:
        column = _resolve_column(self._model, col)
        return self._and(column.between(low, high))

    def or_where_between(self, col: Any, low: Any, high: Any) -> Self:
        column = _resolve_column(self._model, col)
        return self._or(column.between(low, high))

    def where_not_between(self, col: Any, low: Any, high: Any) -> Self:
        column = _resolve_column(self._model, col)
        return self._and(~column.between(low, high))

    def where_null(self, col: Any) -> Self:
        column = _resolve_column(self._model, col)
        return self._and(column.is_(None))

    def or_where_null(self, col: Any) -> Self:
        column = _resolve_column(self._model, col)
        return self._or(column.is_(None))

    def where_not_null(self, col: Any) -> Self:
        column = _resolve_column(self._model, col)
        return self._and(column.is_not(None))

    def or_where_not_null(self, col: Any) -> Self:
        column = _resolve_column(self._model, col)
        return self._or(column.is_not(None))

    def where_raw(self, raw_sql: str, bindings: dict[str, Any] | None = None) -> Self:
        clause = text(raw_sql).bindparams(**(bindings or {}))
        return self._and(clause)

    def or_where_raw(self, raw_sql: str, bindings: dict[str, Any] | None = None) -> Self:
        clause = text(raw_sql).bindparams(**(bindings or {}))
        return self._or(clause)

    def where_column(self, col1: str, col2: str) -> Self:
        c1 = _resolve_column(self._model, col1)
        c2 = _resolve_column(self._model, col2)
        return self._and(c1 == c2)

    # ------------------------------------------------------------------ date/time parts
    # ``extract`` compiles to native EXTRACT on PostgreSQL and to a CAST(STRFTIME(...))
    # on SQLite, so these stay dialect-portable without hand-written SQL per backend.

    def _date_predicate(self, col: Any, value: Any) -> Any:
        import datetime

        d = value if isinstance(value, datetime.date) else datetime.date.fromisoformat(str(value))
        column = _resolve_column(self._model, col)
        return and_(
            extract("year", column) == d.year,
            extract("month", column) == d.month,
            extract("day", column) == d.day,
        )

    def _time_predicate(self, col: Any, value: Any) -> Any:
        import datetime

        t = value if isinstance(value, datetime.time) else datetime.time.fromisoformat(str(value))
        column = _resolve_column(self._model, col)
        return and_(
            extract("hour", column) == t.hour,
            extract("minute", column) == t.minute,
            extract("second", column) == t.second,
        )

    def where_date(self, col: str, value: Any) -> Self:
        return self._and(self._date_predicate(col, value))

    def or_where_date(self, col: str, value: Any) -> Self:
        return self._or(self._date_predicate(col, value))

    def where_time(self, col: str, value: Any) -> Self:
        return self._and(self._time_predicate(col, value))

    def or_where_time(self, col: str, value: Any) -> Self:
        return self._or(self._time_predicate(col, value))

    def where_year(self, col: str, value: int) -> Self:
        return self._and(extract("year", _resolve_column(self._model, col)) == value)

    def or_where_year(self, col: str, value: int) -> Self:
        return self._or(extract("year", _resolve_column(self._model, col)) == value)

    def where_month(self, col: str, value: int) -> Self:
        return self._and(extract("month", _resolve_column(self._model, col)) == value)

    def or_where_month(self, col: str, value: int) -> Self:
        return self._or(extract("month", _resolve_column(self._model, col)) == value)

    def where_day(self, col: str, value: int) -> Self:
        return self._and(extract("day", _resolve_column(self._model, col)) == value)

    def or_where_day(self, col: str, value: int) -> Self:
        return self._or(extract("day", _resolve_column(self._model, col)) == value)

    # ------------------------------------------------------------------ LIKE / multi-column
    # ``pattern`` is always a bind parameter — never interpolated. ``%``/``_`` in user input
    # act as wildcards; callers that need them literal must escape and pass an ``escape`` char
    # via where_raw.

    def _like_clause(self, col: Any, pattern: str, *, case_sensitive: bool) -> Any:
        column = _resolve_column(self._model, col)
        return column.like(pattern) if case_sensitive else column.ilike(pattern)

    def where_like(self, col: str, pattern: str, *, case_sensitive: bool = False) -> Self:
        return self._and(self._like_clause(col, pattern, case_sensitive=case_sensitive))

    def or_where_like(self, col: str, pattern: str, *, case_sensitive: bool = False) -> Self:
        return self._or(self._like_clause(col, pattern, case_sensitive=case_sensitive))

    def where_not_like(self, col: str, pattern: str, *, case_sensitive: bool = False) -> Self:
        return self._and(~self._like_clause(col, pattern, case_sensitive=case_sensitive))

    def or_where_not_like(self, col: str, pattern: str, *, case_sensitive: bool = False) -> Self:
        return self._or(~self._like_clause(col, pattern, case_sensitive=case_sensitive))

    def _multi_col_parts(self, columns: list[str], operator: str, value: Any) -> list[Any]:
        if operator not in _WHERE_ANY_OPS:
            raise ValueError(
                f"Unsupported operator {operator!r}. Valid operators: {sorted(_WHERE_ANY_OPS)}"
            )
        return [_apply_operator(_resolve_column(self._model, c), operator, value) for c in columns]

    def where_all(self, columns: list[str], operator: str, value: Any) -> Self:
        """All listed columns must match (AND)."""
        parts = self._multi_col_parts(columns, operator, value)
        return self._and(and_(*parts)) if parts else self._clone()

    def or_where_all(self, columns: list[str], operator: str, value: Any) -> Self:
        parts = self._multi_col_parts(columns, operator, value)
        return self._or(and_(*parts)) if parts else self._clone()

    def where_none(self, columns: list[str], operator: str, value: Any) -> Self:
        """None of the listed columns match — NOR of the per-column conditions."""
        parts = self._multi_col_parts(columns, operator, value)
        return self._and(~or_(*parts)) if parts else self._clone()

    def or_where_none(self, columns: list[str], operator: str, value: Any) -> Self:
        parts = self._multi_col_parts(columns, operator, value)
        return self._or(~or_(*parts)) if parts else self._clone()

    def or_where_any(self, columns: list[str], operator: str, value: Any) -> Self:
        parts = self._multi_col_parts(columns, operator, value)
        return self._or(or_(*parts)) if parts else self._clone()

    def where_exists(self, subquery_fn: Callable[[QueryBuilder[T]], Any]) -> Self:
        from sqlalchemy import exists as sqla_exists

        sub = subquery_fn(type(self)(self._model))
        sub_stmt = sub.apply_global_scopes() if hasattr(sub, "apply_global_scopes") else sub
        return self._and(sqla_exists(sub_stmt))

    def where_any(self, columns: list[str], operator: str, value: Any) -> Self:
        if operator not in _WHERE_ANY_OPS:
            raise ValueError(
                f"where_any() received unsupported operator {operator!r}. "
                f"Valid operators: {sorted(_WHERE_ANY_OPS)}"
            )
        parts = [_apply_operator(_resolve_column(self._model, c), operator, value) for c in columns]
        if not parts:
            return self._clone()
        return self._and(or_(*parts))

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
        return self._and(sql)

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
        return self._and(sql)

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

    def unless(
        self,
        condition: Any,
        callback: Callable[[Self], Self],
        otherwise: Callable[[Self], Self] | None = None,
    ) -> Self:
        return self.when(not condition, callback, otherwise)

    def tap(self, callback: Callable[[Self], Any]) -> Self:
        """Hand a clone to ``callback`` for side effects; the return value is ignored."""
        clone = self._clone()
        callback(clone)
        return clone

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

    def order_by_desc(self, col: str) -> Self:
        return self._clone(self._stmt.order_by(_resolve_column(self._model, col).desc()))

    def reorder(self, *cols: Any) -> Self:
        """Drop any existing ORDER BY, then optionally apply a new one."""
        cleared = self._clone(self._stmt.order_by(None))
        return cleared.order_by(*cols) if cols else cleared

    def in_random_order(self) -> Self:
        """Order rows randomly. Uses ``random()`` (SQLite/PostgreSQL)."""
        return self._clone(self._stmt.order_by(func.random()))

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
        return self._and(clause)

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

    def group_by_raw(self, raw_sql: str) -> Self:
        return self._clone(self._stmt.group_by(text(raw_sql)))

    def having(self, column: Any, operator: str | None = None, value: Any = _UNSET) -> Self:
        """Add a HAVING clause.

        Pass a ready SQL expression (``having(func.count() > 5)``) or the
        operator form (``having("total", ">", 5)``).
        """
        if operator is None:
            return self._clone(self._stmt.having(column))
        col = _resolve_column(self._model, column) if isinstance(column, str) else column
        return self._clone(self._stmt.having(_apply_operator(col, operator, value)))

    def having_null(self, col: str) -> Self:
        return self._clone(self._stmt.having(_resolve_column(self._model, col).is_(None)))

    def having_between(self, col: str, low: Any, high: Any) -> Self:
        return self._clone(self._stmt.having(_resolve_column(self._model, col).between(low, high)))

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

    def right_join(self, target: type[Any], onclause: Any) -> Self:
        """RIGHT JOIN. SQLAlchemy has no native form, so this rewrites it as
        ``target LEFT OUTER JOIN model`` — the standard, equivalent transform."""
        from sqlalchemy import join as sqla_join

        joined = sqla_join(target, self._model, onclause, isouter=True)
        return self._clone(self._stmt.select_from(joined))

    def cross_join(self, target: type[Any]) -> Self:
        """CROSS JOIN (cartesian product)."""
        from sqlalchemy import true

        return self._clone(self._stmt.join(target, true()))

    def join_on(
        self,
        target: type[Any],
        on: Callable[[JoinOn], Any],
        *,
        kind: str = "inner",
    ) -> Self:
        """Join with a closure-built ON clause supporting ``on``/``or_on``."""
        builder = JoinOn()
        on(builder)
        predicate = builder.build()
        if predicate is None:
            raise ValueError("join_on() closure must add at least one on()/or_on() condition.")
        if kind == "left":
            return self._clone(self._stmt.outerjoin(target, predicate))
        return self._clone(self._stmt.join(target, predicate))

    def from_sub(self, query: QueryBuilder[Any], alias: str) -> Self:
        """Select FROM a derived table (subquery). Rows come back as dicts, not model instances."""
        subq = query.apply_global_scopes().subquery(alias)
        new = self._clone(select(subq).select_from(subq))
        new._where_predicate = None
        new._select_columns = ["__cols__"]
        return new

    def join_sub(
        self,
        query: QueryBuilder[Any],
        alias: str,
        on: Callable[[Any], Any] | Any,
        *,
        kind: str = "inner",
    ) -> Self:
        """JOIN a subquery as a derived table. ``on`` may be a condition or a callable
        receiving the aliased subquery (use ``alias.c.<col>`` to reference its columns)."""
        subq = query.apply_global_scopes().subquery(alias)
        predicate: Any = on(subq) if callable(on) else on
        if kind == "left":
            return self._clone(self._stmt.outerjoin(subq, predicate))
        return self._clone(self._stmt.join(subq, predicate))

    def left_join_sub(
        self, query: QueryBuilder[Any], alias: str, on: Callable[[Any], Any] | Any
    ) -> Self:
        """LEFT JOIN a subquery as a derived table."""
        return self.join_sub(query, alias, on, kind="left")

    def select_sub(self, query: QueryBuilder[Any], alias: str) -> Self:
        """Append a single-column subquery as a correlated scalar column labeled ``alias``."""
        scalar = query.apply_global_scopes().scalar_subquery().label(alias)
        clone = self._clone(self._stmt.add_columns(scalar))
        clone._select_columns = ["__with_agg__"]
        return clone

    def add_select(self, *columns: str | Any) -> Self:
        """Append columns to the SELECT list (model column names or SQLAlchemy expressions)."""
        cols: list[Any] = []
        for c in columns:
            if isinstance(c, str):
                try:
                    cols.append(_resolve_column(self._model, c))
                except AttributeError:
                    cols.append(text(c))
            else:
                cols.append(c)
        clone = self._clone(self._stmt.add_columns(*cols))
        clone._select_columns = ["__with_agg__"]
        return clone

    def with_(
        self,
        *relations: str | Mapping[str, Callable[[QueryBuilder[Any]], QueryBuilder[Any]]],
    ) -> Self:
        stmt = self._stmt
        async_specs: list[_AsyncEagerSpec] = list(self._async_eager)
        for item in relations:
            if isinstance(item, Mapping):
                for path, callback in item.items():
                    if _is_async_relation(self._model, path):
                        async_specs.append(_AsyncEagerSpec(path, callback))
                    else:
                        stmt = stmt.options(
                            _selectin_loader_for_path(self._model, path, constraint=callback)
                        )
            elif type(item) is str:
                if _is_async_relation(self._model, item):
                    async_specs.append(_AsyncEagerSpec(item, None))
                else:
                    stmt = stmt.options(_selectin_loader_for_path(self._model, item))
            else:
                raise TypeError(
                    f"{self._model.__name__}.with_() expects str relation paths or "
                    f"dict[str, callback] mappings, got {type(item).__name__}."
                )
        clone = self._clone(stmt)
        clone._async_eager = async_specs
        return clone

    async def _eager_load_async(self, items: Sequence[Any]) -> None:
        """Run any pending batched MorphToMany/BelongsToMany eager loads."""
        if not self._async_eager or not items:
            return
        parents = list(items)
        for spec in self._async_eager:
            await _load_async_relation_path(self._model, parents, spec.path, spec.constraint)

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
        return self._and(sqla_exists(sub))

    def where_relation(self, relation: str | Any, column: str, value: Any) -> Self:
        """Filter to rows whose related model has ``column == value`` (Eloquent's whereRelation)."""
        return self.where_has(relation, lambda q: q.where(**{column: value}))

    def doesnt_have(self, relation: str | Any) -> Self:
        from sqlalchemy import exists as sqla_exists

        target = _resolve_relation(self._model, relation)
        sub = _exists_subquery(self._model, target)
        return self._and(~sqla_exists(sub))

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
        return self._and(cond)

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
        new = self._clone(cast("Select[Any]", select(self._model).from_statement(combined)))
        # WHERE is already baked into the union operands; don't re-apply it.
        new._where_predicate = None
        return new

    def union_all(self, other: QueryBuilder[Any]) -> Self:
        """UNION ALL (keeps duplicates)."""
        combined = self.apply_global_scopes().union_all(other.apply_global_scopes())
        new = self._clone(cast("Select[Any]", select(self._model).from_statement(combined)))
        new._where_predicate = None
        return new

    # ------------------------------------------------------------------ apply scopes

    def apply_global_scopes(self) -> Select[Any]:
        target: QueryBuilder[Any] = self
        if not self._remove_all_global_scopes:
            scopes: dict[str, Callable[[QueryBuilder[Any]], QueryBuilder[Any]]] = getattr(
                self._model, "__arvel_global_scopes__", {}
            )
            for name, scope_fn in scopes.items():
                if name in self._removed_global_scopes:
                    continue
                target = scope_fn(target)

        stmt = target._stmt
        if target._where_predicate is not None:
            stmt = stmt.where(target._where_predicate)
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
        rb._where_predicate = self._where_predicate
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

    def to_raw_sql(self, *, dialect: str | None = None) -> str:
        """SQL with bindings inlined (Laravel ``toRawSql``) — handy for copy-paste debugging."""
        return self.to_sql(dialect=dialect)

    def get_bindings(self, *, dialect: str | None = None) -> list[Any]:
        """Bound parameter values, in statement order (Laravel ``getBindings``)."""
        stmt = self._apply_locks(self.apply_global_scopes())
        compiled = stmt.compile(dialect=_resolve_sqla_dialect(dialect))
        return list(compiled.params.values())

    async def explain(self) -> list[dict[str, Any]]:
        """Return the dialect's query plan rows (``EXPLAIN`` / ``EXPLAIN QUERY PLAN`` on SQLite)."""
        session = get_active_session()
        dialect_name = (await session.connection()).dialect.name
        prefix = "EXPLAIN QUERY PLAN" if dialect_name == "sqlite" else "EXPLAIN"
        sql = self.to_sql()
        result = await session.execute(text(f"{prefix} {sql}"))
        return [dict(row) for row in result.mappings().all()]

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

    async def _fire_retrieved(self, instances: Sequence[Any]) -> None:
        """Fire the ``retrieved`` event for each hydrated model instance."""
        from arvel.database.events import fire_async

        for instance in instances:
            await fire_async(self._model, "retrieved", instance)

    async def first(self) -> T | None:
        stmt = self.apply_global_scopes().limit(1)
        if self._lock_for_update:
            stmt = stmt.with_for_update()
        elif self._lock_shared:
            stmt = stmt.with_for_update(read=True)
        result = await get_active_session().execute(stmt)
        instance = cast("T | None", result.scalars().first())
        if instance is not None:
            await self._fire_retrieved((instance,))
            await self._eager_load_async((instance,))
        return instance

    async def first_or_fail(self) -> T:
        instance = await self.first()
        if instance is None:
            raise ModelNotFoundError(self._model.__name__, "first()")
        return instance

    async def first_where(self, *clauses: Any, **kwargs: Any) -> T | None:
        """Add a where constraint and return the first matching row (Eloquent's firstWhere)."""
        return await self.where(*clauses, **kwargs).first()

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
        await self._fire_retrieved((rows[0],))
        await self._eager_load_async((rows[0],))
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
            await self._fire_retrieved(items)
            await self._eager_load_async(items)
            return Collection(items)

        result = await get_active_session().execute(stmt)
        scalars = list(result.scalars().all())
        await self._fire_retrieved(scalars)
        await self._eager_load_async(scalars)
        return Collection(scalars)

    async def get(self) -> Any:
        return await self.all()

    async def count(self, column: str | None = None) -> int:
        stmt = self.apply_global_scopes()
        sub = stmt.subquery()
        # COUNT(col) skips NULLs; COUNT(*) counts every row.
        counter = func.count(sub.c[column]) if column is not None else func.count()
        count_stmt = select(counter).select_from(sub)
        result = await get_active_session().execute(count_stmt)
        return int(result.scalar_one())

    async def exists(self) -> bool:
        from sqlalchemy import exists as sqla_exists

        # EXISTS ignores the projected columns but keeps FROM/WHERE; the planner
        # short-circuits on the first matching row instead of counting all of them.
        inner = self.apply_global_scopes().limit(1)
        stmt = select(sqla_exists(inner))
        result = await get_active_session().execute(stmt)
        return bool(result.scalar())

    async def doesnt_exist(self) -> bool:
        return not await self.exists()

    async def value(self, col: str) -> Any:
        column = _resolve_column(self._model, col)
        stmt = self.apply_global_scopes().with_only_columns(column).limit(1)
        result = await get_active_session().execute(stmt)
        return result.scalar()

    async def pluck(self, col: str, key: str | None = None) -> list[Any] | dict[Any, Any]:
        """Return a flat list of one column, or ``{key: value}`` when ``key`` is given."""
        column = _resolve_column(self._model, col)
        if key is None:
            stmt = self.apply_global_scopes().with_only_columns(column)
            result = await get_active_session().execute(stmt)
            return list(result.scalars().all())
        key_col = _resolve_column(self._model, key)
        stmt = self.apply_global_scopes().with_only_columns(key_col, column)
        rows = (await get_active_session().execute(stmt)).all()
        return {row[0]: row[1] for row in rows}

    # ------------------------------------------------------------------ aggregates

    async def sum(self, col: str) -> Any:
        column = _resolve_column(self._model, col)
        stmt = self.apply_global_scopes().with_only_columns(func.sum(column))
        result = await get_active_session().execute(stmt)
        # Laravel returns 0 for an empty set, not null.
        value = result.scalar_one_or_none()
        return value if value is not None else 0

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
        await self._fire_retrieved(items)
        await self._eager_load_async(items)
        return Paginator(items=items, total=total, per_page=per_page, current_page=page)

    async def simple_paginate(self, per_page: int = 15, *, page: int = 1) -> SimplePaginator[T]:
        """No COUNT query — use for large tables or infinite scroll."""
        items_stmt = self.apply_global_scopes().limit(per_page + 1).offset((page - 1) * per_page)
        result = await get_active_session().execute(items_stmt)
        from arvel.support.collections import Collection

        rows: list[T] = cast("list[T]", list(result.scalars().all()))
        has_more = len(rows) > per_page
        page_items = rows[:per_page]
        await self._eager_load_async(page_items)
        return SimplePaginator(
            items=Collection(page_items),
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

        When ``keyset`` is omitted the method uses a single-PK ascending cursor.

        Cursor tokens are opaque ``base64(json(values))`` strings.  The token
        encodes a dict mapping each keyset column to the last row's value so
        the next page starts **after** that position.

        The emitted WHERE clause uses a row-value comparison::

            WHERE (published_at, id) < (:cursor_0, :cursor_1)

        which PostgreSQL evaluates efficiently against a composite index.
        """
        if keyset:
            return await self._keyset_paginate(per_page, cursor=cursor, keyset=keyset)

        # Default single-PK ascending cursor.
        mapper = _mapper_of(self._model)
        pk_col = mapper.primary_key[0]
        pk_key = pk_col.key
        if pk_key is None:
            raise TypeError(f"{self._model.__name__} primary key column has no name.")
        pk_attr = _resolve_column(self._model, pk_key)

        stmt = self.apply_global_scopes().order_by(pk_attr)
        if cursor is not None:
            try:
                last_pk = json.loads(base64.b64decode(cursor.encode()).decode())
            except (ValueError, binascii.Error) as exc:
                raise InvalidCursorError(str(exc)) from exc
            stmt = stmt.where(pk_attr > last_pk)

        result = await get_active_session().execute(stmt.limit(per_page + 1))
        from arvel.support.collections import Collection

        rows: list[T] = cast("list[T]", list(result.scalars().all()))
        has_more = len(rows) > per_page
        items = Collection(rows[:per_page])
        await self._eager_load_async(list(items))
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
            except (ValueError, KeyError, binascii.Error) as exc:
                raise InvalidCursorError(str(exc)) from exc

        result = await get_active_session().execute(stmt.limit(per_page + 1))
        from arvel.support.collections import Collection

        rows: list[T] = cast("list[T]", list(result.scalars().all()))
        has_more = len(rows) > per_page
        items = Collection(rows[:per_page])
        await self._eager_load_async(list(items))
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

    def _ordered_for_offset(self) -> Self:
        """Enforce a stable order for OFFSET pagination, like Eloquent's chunk().

        OFFSET without an order can skip or repeat rows. If no ``order_by`` is
        set, fall back to the model's primary key.
        """
        if getattr(self._stmt, "_order_by_clauses", ()):
            return self
        mapper: Mapper[Any] = cast("Mapper[Any]", sqla_inspect(self._model))
        return self._clone(self._stmt.order_by(*mapper.primary_key))

    async def _keyset_batches(
        self, size: int, column: str, descending: bool
    ) -> AsyncGenerator[list[T]]:
        """Walk a keyset on ``column`` in batches, in the requested direction.

        Backs chunk_by_id / lazy / lazy_by_id. Stable under concurrent
        inserts/deletes — rows can't be skipped or seen twice the way
        OFFSET-based chunk() can.
        """
        col = _resolve_column(self._model, column)
        last_id: Any = None
        while True:
            stmt = self.apply_global_scopes()
            if last_id is not None:
                stmt = stmt.where(col < last_id if descending else col > last_id)
            stmt = stmt.order_by(col.desc() if descending else col).limit(size)
            result = await get_active_session().execute(stmt)
            batch: list[T] = cast("list[T]", list(result.scalars().all()))
            if not batch:
                return
            await self._fire_retrieved(batch)
            await self._eager_load_async(batch)
            yield batch
            if len(batch) < size:
                return
            last_id = getattr(batch[-1], column)

    async def chunk(
        self, size: int, callback: Callable[[list[T]], Awaitable[bool | None]]
    ) -> None:
        """Process rows in OFFSET batches. Return ``False`` from the callback to stop."""
        base = self._ordered_for_offset()
        page = 1
        while True:
            stmt = base.apply_global_scopes().limit(size).offset((page - 1) * size)
            result = await get_active_session().execute(stmt)
            batch: list[T] = cast("list[T]", list(result.scalars().all()))
            if not batch:
                return
            await self._fire_retrieved(batch)
            await self._eager_load_async(batch)
            if await callback(batch) is False:
                return
            if len(batch) < size:
                return
            page += 1

    async def chunk_by_id(
        self,
        size: int,
        callback: Callable[[list[T]], Awaitable[bool | None]],
        *,
        column: str = "id",
        descending: bool = False,
    ) -> None:
        """Chunk by a keyset on ``column`` instead of OFFSET.

        ``descending=True`` walks the key high-to-low. Return ``False`` from the
        callback to stop.
        """
        async for batch in self._keyset_batches(size, column, descending):
            if await callback(batch) is False:
                return

    async def lazy(self, chunk_size: int = 1000, *, column: str = "id") -> AsyncGenerator[T]:
        """Stream rows one at a time, fetching in ascending keyset batches."""
        async for row in self.lazy_by_id(chunk_size, column=column):
            yield row

    async def lazy_by_id(
        self, chunk_size: int = 1000, *, column: str = "id", descending: bool = False
    ) -> AsyncGenerator[T]:
        """Stream rows one at a time over a keyset, in the requested direction."""
        async for batch in self._keyset_batches(chunk_size, column, descending):
            for row in batch:
                yield row

    def cursor(self, chunk_size: int = 1000, *, column: str = "id") -> AsyncGenerator[T]:
        """Alias for :meth:`lazy` — stream rows without loading them all at once."""
        return self.lazy(chunk_size, column=column)

    async def stream(self, *, batch_size: int = 1000) -> AsyncGenerator[T]:
        """Server-side cursor: one statement, rows fetched incrementally from the driver.

        Distinct from :meth:`lazy` (which issues N keyset queries). Fires ``retrieved``
        per row and does not batch-eager-load pivots — use :meth:`lazy`/:meth:`chunk`
        for that.
        """
        stmt = self.apply_global_scopes().execution_options(yield_per=batch_size)
        result = await get_active_session().stream_scalars(stmt)
        async for row in result:
            typed = cast("T", row)
            await self._fire_retrieved((typed,))
            yield typed

    async def each(self, callback: Callable[[T], Awaitable[bool | None]]) -> None:
        """Process rows one at a time. Return ``False`` from the callback to stop."""

        async def _per_batch(batch: list[T]) -> bool | None:
            for item in batch:
                if await callback(item) is False:
                    return False
            return None

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

    def _touch_updated_at(self, values: dict[str, Any]) -> dict[str, Any]:
        """Merge ``updated_at = now()`` for timestamped models, like Eloquent's bulk update."""
        table = _table_of(self._model)
        if "updated_at" in table.c and "updated_at" not in values:
            from datetime import UTC, datetime

            return {**values, "updated_at": datetime.now(UTC)}
        return values

    async def update(self, values: dict[str, Any]) -> int:
        self._assert_writable("update")
        from sqlalchemy import update as sqla_update

        session = get_active_session()
        table = _table_of(self._model)
        stmt = sqla_update(table)
        where_clause = self.apply_global_scopes().whereclause
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        stmt = stmt.values(**self._touch_updated_at(values))
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

    def _native_unique_columns(self) -> set[str]:
        """Column names covered by the table's PK or a UNIQUE constraint."""
        from sqlalchemy import UniqueConstraint

        table = _table_of(self._model)
        cols: set[str] = {col.name for col in table.primary_key}
        for constraint in table.constraints:
            if isinstance(constraint, UniqueConstraint):
                cols.update(col.name for col in constraint.columns)
        return cols

    async def insert_or_ignore(self, rows: list[dict[str, Any]]) -> int:
        """INSERT rows, skipping any that violate a unique constraint. Returns rows inserted.

        ON CONFLICT DO NOTHING on SQLite/PostgreSQL, INSERT IGNORE on MySQL. Other dialects
        fall back to a plain insert (no conflict suppression).
        """
        self._assert_writable("insert_or_ignore")
        if not rows:
            return 0
        session = get_active_session()
        table = _table_of(self._model)
        dialect_name = (await session.connection()).dialect.name

        stmt: Any
        if dialect_name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            stmt = sqlite_insert(table).values(rows).on_conflict_do_nothing()
        elif dialect_name in ("postgresql", "postgres"):
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            stmt = pg_insert(table).values(rows).on_conflict_do_nothing()
        elif dialect_name == "mysql":
            from sqlalchemy.dialects.mysql import insert as mysql_insert

            stmt = mysql_insert(table).values(rows).prefix_with("IGNORE")
        else:
            from sqlalchemy import insert as sqla_insert

            stmt = sqla_insert(table).values(rows)

        result = cast("CursorResult[Any]", await session.execute(stmt))
        await session.flush()
        return int(result.rowcount) if result.rowcount != -1 else len(rows)

    async def upsert(
        self,
        rows: list[dict[str, Any]],
        *,
        unique_by: list[str],
        update: list[str],
    ) -> int:
        """INSERT … ON CONFLICT DO UPDATE as a single multi-row statement; returns affected rows.

        Falls back to a per-row check-and-write when ``unique_by`` isn't backed by a PK/UNIQUE
        constraint or the dialect has no native upsert.
        """
        self._assert_writable("upsert")
        if not rows:
            return 0
        session = get_active_session()
        table = _table_of(self._model)
        dialect_name: str = (await session.connection()).dialect.name
        has_constraint = all(c in self._native_unique_columns() for c in unique_by)

        stmt: Any
        base: Any
        if has_constraint and dialect_name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            base = sqlite_insert(table).values(rows)
            stmt = base.on_conflict_do_update(
                index_elements=unique_by,
                set_={k: getattr(base.excluded, k) for k in update},
            )
        elif has_constraint and dialect_name in ("postgresql", "postgres"):
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            base = pg_insert(table).values(rows)
            stmt = base.on_conflict_do_update(
                index_elements=unique_by,
                set_={k: getattr(base.excluded, k) for k in update},
            )
        elif has_constraint and dialect_name == "mysql":
            from sqlalchemy.dialects.mysql import insert as mysql_insert

            base = mysql_insert(table).values(rows)
            stmt = base.on_duplicate_key_update({k: getattr(base.inserted, k) for k in update})
        else:
            return await self._upsert_manual(rows, unique_by=unique_by, update=update)

        result = cast("CursorResult[Any]", await session.execute(stmt))
        await session.flush()
        return int(result.rowcount) if result.rowcount != -1 else len(rows)

    async def _upsert_manual(
        self,
        rows: list[dict[str, Any]],
        *,
        unique_by: list[str],
        update: list[str],
    ) -> int:
        affected = 0
        for row in rows:
            where_dict = {k: row[k] for k in unique_by if k in row}
            qb = type(self)(self._model).where(**where_dict)
            if await qb.count() > 0:
                affected += await qb.update({k: row[k] for k in update if k in row})
            else:
                await type(self)(self._model).insert([row])
                affected += 1
        return affected

    async def insert_using(self, columns: list[str], query: QueryBuilder[Any]) -> int:
        """INSERT INTO … (columns) SELECT … — populate from another query. Returns rows inserted."""
        self._assert_writable("insert_using")
        from sqlalchemy import insert as sqla_insert

        session = get_active_session()
        table = _table_of(self._model)
        stmt = sqla_insert(table).from_select(columns, query.apply_global_scopes())
        result = cast("CursorResult[Any]", await session.execute(stmt))
        await session.flush()
        return int(result.rowcount) if result.rowcount != -1 else 0

    async def truncate(self) -> None:
        """Empty the mapped table.

        PostgreSQL/MySQL issue ``TRUNCATE`` (resets identity, ignores soft-delete — this is a
        hard wipe). SQLite has no TRUNCATE, so it falls back to ``DELETE`` without a WHERE.
        """
        self._assert_writable("truncate")
        session = get_active_session()
        conn = await session.connection()
        table = _table_of(self._model)
        dialect_name = conn.dialect.name
        if dialect_name in ("postgresql", "postgres", "mysql"):
            quoted = conn.dialect.identifier_preparer.format_table(table)
            await session.execute(text(f"TRUNCATE TABLE {quoted}"))
        else:
            from sqlalchemy import delete as sqla_delete

            await session.execute(sqla_delete(table))
        await session.flush()

    async def increment(
        self, col: str, amount: int = 1, *, extra: dict[str, Any] | None = None
    ) -> int:
        """Increment ``col`` by ``amount``, set any ``extra`` columns, return rows affected."""
        self._assert_writable("increment")
        from sqlalchemy import update as sqla_update

        session = get_active_session()
        table = _table_of(self._model)
        db_col = table.c[col]
        values: dict[str, Any] = {col: db_col + amount, **(extra or {})}
        stmt = sqla_update(table).values(self._touch_updated_at(values))
        where_clause = self.apply_global_scopes().whereclause
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        result = cast("CursorResult[Any]", await session.execute(stmt))
        await session.flush()
        return int(result.rowcount)

    async def decrement(
        self, col: str, amount: int = 1, *, extra: dict[str, Any] | None = None
    ) -> int:
        """Decrement ``col`` by ``amount``, set any ``extra`` columns, return rows affected."""
        return await self.increment(col, -amount, extra=extra)

    async def increment_each(
        self, amounts: dict[str, int], *, extra: dict[str, Any] | None = None
    ) -> int:
        """Bump several columns in one UPDATE: ``{col: delta}``. Returns rows affected."""
        self._assert_writable("increment_each")
        from sqlalchemy import update as sqla_update

        session = get_active_session()
        table = _table_of(self._model)
        values: dict[str, Any] = {col: table.c[col] + delta for col, delta in amounts.items()}
        if extra:
            values.update(extra)
        stmt = sqla_update(table).values(self._touch_updated_at(values))
        where_clause = self.apply_global_scopes().whereclause
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        result = cast("CursorResult[Any]", await session.execute(stmt))
        await session.flush()
        return int(result.rowcount)

    async def decrement_each(
        self, amounts: dict[str, int], *, extra: dict[str, Any] | None = None
    ) -> int:
        """Decrement several columns in one UPDATE: ``{col: delta}``. Returns rows affected."""
        return await self.increment_each({c: -d for c, d in amounts.items()}, extra=extra)

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
            soft_values = self._touch_updated_at({soft_field: datetime.now(UTC)})
            stmt = sqla_update(table).values(soft_values)
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
        await self._eager_load_async(rows)
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
