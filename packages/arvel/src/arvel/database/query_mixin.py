"""QueryMixin — typed classmethods that forward to query().

Inherit this to get fully-typed, IDE-friendly query entry points on any
Model subclass without calling query() explicitly.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Any, Self, cast

if TYPE_CHECKING:
    from sqlalchemy.orm import InstrumentedAttribute
    from sqlalchemy.sql.selectable import CTE

    from arvel.database.paginator import Paginator
    from arvel.database.query import (
        CursorPaginator,
        JoinOn,
        QueryBuilder,
        RecursiveQueryBuilder,
        SimplePaginator,
    )


class QueryMixin:
    """Typed class-level query shortcuts.

    Every method creates a fresh ``QueryBuilder[_M]`` and applies the
    corresponding operation, giving callers full type inference without
    an explicit ``query()`` call.
    """

    @classmethod
    def query(cls) -> QueryBuilder[Self]:
        from arvel.database.query import QueryBuilder

        return QueryBuilder(cls)

    # ── filters ───────────────────────────────────────────────────────────

    @classmethod
    def where(cls, *clauses: Any, **kwargs: Any) -> QueryBuilder[Self]:
        return cls.query().where(*clauses, **kwargs)

    @classmethod
    def or_where(cls, *clauses: Any, **kwargs: Any) -> QueryBuilder[Self]:
        return cls.query().or_where(*clauses, **kwargs)

    @classmethod
    def where_in(cls, col: Any, values: Iterable[Any]) -> QueryBuilder[Self]:
        return cls.query().where_in(col, values)

    @classmethod
    def where_not_in(cls, col: Any, values: Iterable[Any]) -> QueryBuilder[Self]:
        return cls.query().where_not_in(col, values)

    @classmethod
    def where_between(cls, col: Any, low: Any, high: Any) -> QueryBuilder[Self]:
        return cls.query().where_between(col, low, high)

    @classmethod
    def where_not_between(cls, col: Any, low: Any, high: Any) -> QueryBuilder[Self]:
        return cls.query().where_not_between(col, low, high)

    @classmethod
    def where_null(cls, col: Any) -> QueryBuilder[Self]:
        return cls.query().where_null(col)

    @classmethod
    def where_not_null(cls, col: Any) -> QueryBuilder[Self]:
        return cls.query().where_not_null(col)

    @classmethod
    def or_where_in(cls, col: Any, values: Iterable[Any]) -> QueryBuilder[Self]:
        return cls.query().or_where_in(col, values)

    @classmethod
    def or_where_not_in(cls, col: Any, values: Iterable[Any]) -> QueryBuilder[Self]:
        return cls.query().or_where_not_in(col, values)

    @classmethod
    def or_where_between(cls, col: Any, low: Any, high: Any) -> QueryBuilder[Self]:
        return cls.query().or_where_between(col, low, high)

    @classmethod
    def or_where_null(cls, col: Any) -> QueryBuilder[Self]:
        return cls.query().or_where_null(col)

    @classmethod
    def or_where_not_null(cls, col: Any) -> QueryBuilder[Self]:
        return cls.query().or_where_not_null(col)

    @classmethod
    def or_where_raw(
        cls, raw_sql: str, bindings: dict[str, Any] | None = None
    ) -> QueryBuilder[Self]:
        return cls.query().or_where_raw(raw_sql, bindings)

    @classmethod
    def where_date(cls, col: str, value: Any) -> QueryBuilder[Self]:
        return cls.query().where_date(col, value)

    @classmethod
    def or_where_date(cls, col: str, value: Any) -> QueryBuilder[Self]:
        return cls.query().or_where_date(col, value)

    @classmethod
    def where_time(cls, col: str, value: Any) -> QueryBuilder[Self]:
        return cls.query().where_time(col, value)

    @classmethod
    def or_where_time(cls, col: str, value: Any) -> QueryBuilder[Self]:
        return cls.query().or_where_time(col, value)

    @classmethod
    def where_year(cls, col: str, value: int) -> QueryBuilder[Self]:
        return cls.query().where_year(col, value)

    @classmethod
    def or_where_year(cls, col: str, value: int) -> QueryBuilder[Self]:
        return cls.query().or_where_year(col, value)

    @classmethod
    def where_month(cls, col: str, value: int) -> QueryBuilder[Self]:
        return cls.query().where_month(col, value)

    @classmethod
    def or_where_month(cls, col: str, value: int) -> QueryBuilder[Self]:
        return cls.query().or_where_month(col, value)

    @classmethod
    def where_day(cls, col: str, value: int) -> QueryBuilder[Self]:
        return cls.query().where_day(col, value)

    @classmethod
    def or_where_day(cls, col: str, value: int) -> QueryBuilder[Self]:
        return cls.query().or_where_day(col, value)

    @classmethod
    def where_like(
        cls, col: str, pattern: str, *, case_sensitive: bool = False
    ) -> QueryBuilder[Self]:
        return cls.query().where_like(col, pattern, case_sensitive=case_sensitive)

    @classmethod
    def or_where_like(
        cls, col: str, pattern: str, *, case_sensitive: bool = False
    ) -> QueryBuilder[Self]:
        return cls.query().or_where_like(col, pattern, case_sensitive=case_sensitive)

    @classmethod
    def where_not_like(
        cls, col: str, pattern: str, *, case_sensitive: bool = False
    ) -> QueryBuilder[Self]:
        return cls.query().where_not_like(col, pattern, case_sensitive=case_sensitive)

    @classmethod
    def or_where_not_like(
        cls, col: str, pattern: str, *, case_sensitive: bool = False
    ) -> QueryBuilder[Self]:
        return cls.query().or_where_not_like(col, pattern, case_sensitive=case_sensitive)

    @classmethod
    def where_all(cls, columns: list[str], operator: str, value: Any) -> QueryBuilder[Self]:
        return cls.query().where_all(columns, operator, value)

    @classmethod
    def or_where_all(cls, columns: list[str], operator: str, value: Any) -> QueryBuilder[Self]:
        return cls.query().or_where_all(columns, operator, value)

    @classmethod
    def where_none(cls, columns: list[str], operator: str, value: Any) -> QueryBuilder[Self]:
        return cls.query().where_none(columns, operator, value)

    @classmethod
    def or_where_none(cls, columns: list[str], operator: str, value: Any) -> QueryBuilder[Self]:
        return cls.query().or_where_none(columns, operator, value)

    @classmethod
    def or_where_any(cls, columns: list[str], operator: str, value: Any) -> QueryBuilder[Self]:
        return cls.query().or_where_any(columns, operator, value)

    @classmethod
    def where_raw(
        cls,
        raw_sql: str,
        bindings: dict[str, Any] | None = None,
    ) -> QueryBuilder[Self]:
        return cls.query().where_raw(raw_sql, bindings)

    @classmethod
    def where_json_contains(
        cls,
        col: str | InstrumentedAttribute[Any],
        value: Any,
    ) -> QueryBuilder[Self]:
        return cls.query().where_json_contains(col, value)

    @classmethod
    def where_json_path(
        cls,
        col: str | InstrumentedAttribute[Any],
        path: str,
        value: Any,
    ) -> QueryBuilder[Self]:
        return cls.query().where_json_path(col, path, value)

    @classmethod
    def where_column(cls, col1: str, col2: str) -> QueryBuilder[Self]:
        return cls.query().where_column(col1, col2)

    @classmethod
    def where_exists(
        cls,
        subquery_fn: Callable[[QueryBuilder[Any]], Any],
    ) -> QueryBuilder[Self]:
        return cls.query().where_exists(subquery_fn)

    @classmethod
    def where_any(cls, columns: list[str], operator: str, value: Any) -> QueryBuilder[Self]:
        return cls.query().where_any(columns, operator, value)

    @classmethod
    def where_has(
        cls,
        relation: str | Any,
        constraint: Callable[[QueryBuilder[Any]], QueryBuilder[Any]] | None = None,
    ) -> QueryBuilder[Self]:
        return cls.query().where_has(relation, constraint)

    @classmethod
    def doesnt_have(cls, relation: str | Any) -> QueryBuilder[Self]:
        return cls.query().doesnt_have(relation)

    @classmethod
    def where_relation(cls, relation: str | Any, column: str, value: Any) -> QueryBuilder[Self]:
        return cls.query().where_relation(relation, column, value)

    @classmethod
    def has(cls, relation: str | Any, operator: str = ">=", count: int = 1) -> QueryBuilder[Self]:
        return cls.query().has(relation, operator, count)

    @classmethod
    def where_pivot(cls, column: str, value: Any) -> QueryBuilder[Self]:
        # Class-level shortcut. The plain QueryBuilder raises RuntimeError —
        # only BelongsToMany accessors set the pivot table. Mirrors Laravel's
        # __callStatic forwarding.
        return cls.query().where_pivot(column, value)

    # ── ordering ──────────────────────────────────────────────────────────

    @classmethod
    def order_by(cls, *cols: Any) -> QueryBuilder[Self]:
        return cls.query().order_by(*cols)

    @classmethod
    def order_by_raw(cls, raw_sql: str) -> QueryBuilder[Self]:
        return cls.query().order_by_raw(raw_sql)

    @classmethod
    def order_by_desc(cls, col: str) -> QueryBuilder[Self]:
        return cls.query().order_by_desc(col)

    @classmethod
    def reorder(cls, *cols: Any) -> QueryBuilder[Self]:
        return cls.query().reorder(*cols)

    @classmethod
    def in_random_order(cls) -> QueryBuilder[Self]:
        return cls.query().in_random_order()

    @classmethod
    def where_full_text(
        cls,
        col: InstrumentedAttribute[Any],
        query: str,
        *,
        tsquery_fn: str = "plainto_tsquery",
        lang: str = "english",
    ) -> QueryBuilder[Self]:
        return cls.query().where_full_text(col, query, tsquery_fn=tsquery_fn, lang=lang)

    @classmethod
    def order_by_relevance(
        cls,
        col: InstrumentedAttribute[Any],
        query: str,
        *,
        lang: str = "english",
    ) -> QueryBuilder[Self]:
        return cls.query().order_by_relevance(col, query, lang=lang)

    @classmethod
    def latest(cls, col: str = "created_at") -> QueryBuilder[Self]:
        return cls.query().latest(col)

    @classmethod
    def oldest(cls, col: str = "created_at") -> QueryBuilder[Self]:
        return cls.query().oldest(col)

    # ── limit / offset ────────────────────────────────────────────────────

    @classmethod
    def limit(cls, n: int) -> QueryBuilder[Self]:
        return cls.query().limit(n)

    @classmethod
    def offset(cls, n: int) -> QueryBuilder[Self]:
        return cls.query().offset(n)

    # ── grouping ──────────────────────────────────────────────────────────

    @classmethod
    def group_by(cls, *cols: Any) -> QueryBuilder[Self]:
        return cls.query().group_by(*cols)

    @classmethod
    def group_by_raw(cls, raw_sql: str) -> QueryBuilder[Self]:
        return cls.query().group_by_raw(raw_sql)

    @classmethod
    def having(
        cls, column: Any, operator: str | None = None, value: Any = None
    ) -> QueryBuilder[Self]:
        qb = cls.query()
        return qb.having(column) if operator is None else qb.having(column, operator, value)

    @classmethod
    def having_null(cls, col: str) -> QueryBuilder[Self]:
        return cls.query().having_null(col)

    @classmethod
    def having_between(cls, col: str, low: Any, high: Any) -> QueryBuilder[Self]:
        return cls.query().having_between(col, low, high)

    @classmethod
    def having_raw(
        cls,
        raw_sql: str,
        bindings: dict[str, Any] | None = None,
    ) -> QueryBuilder[Self]:
        return cls.query().having_raw(raw_sql, bindings)

    # ── column selection ──────────────────────────────────────────────────

    @classmethod
    def select(cls, *columns: str) -> QueryBuilder[Self]:
        return cls.query().select(*columns)

    @classmethod
    def select_raw(cls, raw_sql: str) -> QueryBuilder[Self]:
        return cls.query().select_raw(raw_sql)

    @classmethod
    def distinct(cls, *cols: Any) -> QueryBuilder[Self]:
        return cls.query().distinct(*cols)

    # ── joins ─────────────────────────────────────────────────────────────

    @classmethod
    def join(cls, target: type[Any], *clauses: Any, **kwargs: Any) -> QueryBuilder[Self]:
        return cls.query().join(target, *clauses, **kwargs)

    @classmethod
    def left_join(cls, target: type[Any], *clauses: Any, **kwargs: Any) -> QueryBuilder[Self]:
        return cls.query().left_join(target, *clauses, **kwargs)

    @classmethod
    def right_join(cls, target: type[Any], onclause: Any) -> QueryBuilder[Self]:
        return cls.query().right_join(target, onclause)

    @classmethod
    def cross_join(cls, target: type[Any]) -> QueryBuilder[Self]:
        return cls.query().cross_join(target)

    @classmethod
    def join_on(
        cls, target: type[Any], on: Callable[[JoinOn], Any], *, kind: str = "inner"
    ) -> QueryBuilder[Self]:
        return cls.query().join_on(target, on, kind=kind)

    # ── eager loading ─────────────────────────────────────────────────────

    @classmethod
    def with_(
        cls,
        *relations: str | Mapping[str, Callable[[QueryBuilder[Any]], QueryBuilder[Any]]],
    ) -> QueryBuilder[Self]:
        return cls.query().with_(*relations)

    @classmethod
    def with_count(cls, *relations: str) -> QueryBuilder[Self]:
        return cls.query().with_count(*relations)

    @classmethod
    def with_sum(cls, relation: str, col: str) -> QueryBuilder[Self]:
        return cls.query().with_sum(relation, col)

    @classmethod
    def with_max(cls, relation: str, col: str) -> QueryBuilder[Self]:
        return cls.query().with_max(relation, col)

    # ── conditional ───────────────────────────────────────────────────────

    @classmethod
    def when(
        cls,
        condition: Any,
        callback: Callable[[QueryBuilder[Self]], QueryBuilder[Self]],
        otherwise: Callable[[QueryBuilder[Self]], QueryBuilder[Self]] | None = None,
    ) -> QueryBuilder[Self]:
        return cls.query().when(condition, callback, otherwise)

    @classmethod
    def unless(
        cls,
        condition: Any,
        callback: Callable[[QueryBuilder[Self]], QueryBuilder[Self]],
        otherwise: Callable[[QueryBuilder[Self]], QueryBuilder[Self]] | None = None,
    ) -> QueryBuilder[Self]:
        return cls.query().unless(condition, callback, otherwise)

    @classmethod
    def tap(cls, callback: Callable[[QueryBuilder[Self]], Any]) -> QueryBuilder[Self]:
        return cls.query().tap(callback)

    # ── global scopes / soft deletes ──────────────────────────────────────

    @classmethod
    def without_global_scope(cls, name: str) -> QueryBuilder[Self]:
        return cls.query().without_global_scope(name)

    @classmethod
    def without_global_scopes(cls) -> QueryBuilder[Self]:
        return cls.query().without_global_scopes()

    @classmethod
    def with_trashed(cls) -> QueryBuilder[Self]:
        return cls.query().with_trashed()

    @classmethod
    def only_trashed(cls) -> QueryBuilder[Self]:
        return cls.query().only_trashed()

    # ── locking ───────────────────────────────────────────────────────────

    @classmethod
    def lock_for_update(cls) -> QueryBuilder[Self]:
        return cls.query().lock_for_update()

    # ── set operations ────────────────────────────────────────────────────

    @classmethod
    def union(cls, other: QueryBuilder[Any]) -> QueryBuilder[Self]:
        return cls.query().union(other)

    @classmethod
    def union_all(cls, other: QueryBuilder[Any]) -> QueryBuilder[Self]:
        return cls.query().union_all(other)

    # ── CTEs / recursive ─────────────────────────────────────────────────

    @classmethod
    def with_cte(cls, name: str, cte: CTE) -> QueryBuilder[Self]:
        return cls.query().with_cte(name, cte)

    @classmethod
    def recursive(
        cls,
        parent_key: str,
        *,
        id_key: str = "id",
        depth_col: str | None = None,
        path_col: str | None = None,
    ) -> RecursiveQueryBuilder[Self]:
        return cls.query().recursive(
            parent_key,
            id_key=id_key,
            depth_col=depth_col,
            path_col=path_col,
        )

    # ── terminal (read) ───────────────────────────────────────────────────

    @classmethod
    async def all(cls) -> list[Self]:
        return cast("list[Self]", await cls.query().all())

    @classmethod
    async def get(cls) -> list[Self]:
        return cast("list[Self]", await cls.query().get())

    @classmethod
    async def first(cls) -> Self | None:
        return await cls.query().first()

    @classmethod
    async def first_where(cls, *clauses: Any, **kwargs: Any) -> Self | None:
        return await cls.query().first_where(*clauses, **kwargs)

    @classmethod
    async def first_or_fail(cls) -> Self:
        return await cls.query().first_or_fail()

    @classmethod
    async def first_or(cls, callback: Callable[[], Self]) -> Self:
        return await cls.query().first_or(callback)

    @classmethod
    async def sole(cls) -> Self:
        return await cls.query().sole()

    @classmethod
    async def count(cls, column: str | None = None) -> int:
        return await cls.query().count(column)

    @classmethod
    async def exists(cls) -> bool:
        return await cls.query().exists()

    @classmethod
    async def doesnt_exist(cls) -> bool:
        return await cls.query().doesnt_exist()

    @classmethod
    async def value(cls, col: str) -> Any:
        return await cls.query().value(col)

    @classmethod
    async def pluck(cls, col: str, key: str | None = None) -> list[Any] | dict[Any, Any]:
        return await cls.query().pluck(col, key)

    # ── aggregates ────────────────────────────────────────────────────────

    @classmethod
    async def sum(cls, col: str) -> Any:
        return await cls.query().sum(col)

    @classmethod
    async def avg(cls, col: str) -> Any:
        return await cls.query().avg(col)

    @classmethod
    async def max(cls, col: str) -> Any:
        return await cls.query().max(col)

    @classmethod
    async def min(cls, col: str) -> Any:
        return await cls.query().min(col)

    # ── pagination ────────────────────────────────────────────────────────

    @classmethod
    async def paginate(cls, per_page: int = 15, *, page: int = 1) -> Paginator[Self]:
        return await cls.query().paginate(per_page, page=page)

    @classmethod
    async def simple_paginate(cls, per_page: int = 15, *, page: int = 1) -> SimplePaginator[Self]:
        return await cls.query().simple_paginate(per_page, page=page)

    @classmethod
    async def cursor_paginate(
        cls, per_page: int = 15, *, cursor: str | None = None
    ) -> CursorPaginator[Self]:
        return await cls.query().cursor_paginate(per_page, cursor=cursor)

    # ── iteration ─────────────────────────────────────────────────────────

    @classmethod
    async def chunk(
        cls,
        size: int,
        callback: Callable[[list[Self]], Awaitable[bool | None]],
    ) -> None:
        await cls.query().chunk(size, callback)

    @classmethod
    async def chunk_by_id(
        cls,
        size: int,
        callback: Callable[[list[Self]], Awaitable[bool | None]],
        *,
        column: str = "id",
        descending: bool = False,
    ) -> None:
        await cls.query().chunk_by_id(size, callback, column=column, descending=descending)

    @classmethod
    def lazy(cls, chunk_size: int = 1000, *, column: str = "id") -> AsyncGenerator[Self]:
        return cls.query().lazy(chunk_size, column=column)

    @classmethod
    def lazy_by_id(
        cls, chunk_size: int = 1000, *, column: str = "id", descending: bool = False
    ) -> AsyncGenerator[Self]:
        return cls.query().lazy_by_id(chunk_size, column=column, descending=descending)

    @classmethod
    def cursor(cls, chunk_size: int = 1000, *, column: str = "id") -> AsyncGenerator[Self]:
        return cls.query().cursor(chunk_size, column=column)

    @classmethod
    def stream(cls, *, batch_size: int = 1000) -> AsyncGenerator[Self]:
        return cls.query().stream(batch_size=batch_size)

    @classmethod
    async def each(
        cls,
        callback: Callable[[Self], Awaitable[bool | None]],
    ) -> None:
        await cls.query().each(callback)

    # ── debug ─────────────────────────────────────────────────────────────

    @classmethod
    def to_sql(cls, *, dialect: str | None = None) -> str:
        return cls.query().to_sql(dialect=dialect)

    # ── write ─────────────────────────────────────────────────────────────

    @classmethod
    async def insert(cls, rows: list[dict[str, Any]]) -> None:
        await cls.query().insert(rows)

    @classmethod
    async def insert_get_id(cls, row: dict[str, Any]) -> Any:
        return await cls.query().insert_get_id(row)

    @classmethod
    async def update(cls, values: dict[str, Any]) -> int:
        return await cls.query().update(values)

    @classmethod
    async def update_or_insert(
        cls,
        *,
        where: dict[str, Any],
        values: dict[str, Any],
    ) -> None:
        await cls.query().update_or_insert(where=where, values=values)

    @classmethod
    async def update_or_create(cls, attributes: dict[str, Any], values: dict[str, Any]) -> Self:
        return await cls.query().update_or_create(attributes, values)

    @classmethod
    async def first_or_create(
        cls, attributes: dict[str, Any], values: dict[str, Any] | None = None
    ) -> Self:
        return await cls.query().first_or_create(attributes, values)

    @classmethod
    async def first_or_new(
        cls, attributes: dict[str, Any], values: dict[str, Any] | None = None
    ) -> Self:
        return await cls.query().first_or_new(attributes, values)

    @classmethod
    async def upsert(
        cls,
        rows: list[dict[str, Any]],
        *,
        unique_by: list[str],
        update: list[str],
    ) -> None:
        await cls.query().upsert(rows, unique_by=unique_by, update=update)

    @classmethod
    async def increment(
        cls, col: str, amount: int = 1, *, extra: dict[str, Any] | None = None
    ) -> int:
        return await cls.query().increment(col, amount, extra=extra)

    @classmethod
    async def decrement(
        cls, col: str, amount: int = 1, *, extra: dict[str, Any] | None = None
    ) -> int:
        return await cls.query().decrement(col, amount, extra=extra)


__all__ = ["QueryMixin"]
