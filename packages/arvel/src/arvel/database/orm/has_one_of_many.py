"""HasOneOfMany — "has one of many" aggregated relation (Laravel's latestOfMany / ofMany).

Picks exactly one related row per owner — the one with MAX (latest) or MIN (oldest)
of a column. Unlike `has_one`, this is a descriptor, so it eager-loads through
`with_()` with a single grouped subquery instead of N+1 per-owner lookups.
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar, cast

from sqlalchemy import func as sqla_func
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.orm import Mapper

from arvel.database.orm._eager import get_eager_relation, set_eager_relation
from arvel.database.session import get_active_session
from arvel.support.str import Str

if TYPE_CHECKING:
    from arvel.database.model import Model

T = TypeVar("T")

Aggregate = Literal["max", "min"]


def _pk_key(model_cls: type[Any]) -> str:
    mapper: Mapper[Any] = cast("Mapper[Any]", sa_inspect(model_cls))
    key = mapper.primary_key[0].key
    if key is None:
        raise TypeError(f"{model_cls.__name__} primary key column has no key")
    return key


@dataclass(frozen=True)
class HasOneOfManyLink:
    """Resolved metadata for a HasOneOfMany, used by the query builder."""

    related_model: type[Any]
    foreign_key: str
    column: str
    aggregate: Aggregate
    owner_pk_key: str


class HasOneOfManyAccessor(Generic[T]):
    """Accessor for a has-one-of-many relation. Awaitable: ``await post.latest_comment``."""

    def __init__(
        self,
        owner: Model,
        related_model: type[T],
        foreign_key: str,
        column: str,
        aggregate: Aggregate,
        attr_name: str | None,
    ) -> None:
        self._owner = owner
        self._related_model = related_model
        self._fk = foreign_key
        self._column = column
        self._aggregate = aggregate
        self._attr_name = attr_name

    def __await__(self) -> Generator[Any, None, T | None]:
        return self.query().__await__()

    async def query(self) -> T | None:
        if self._attr_name is not None:
            cached = get_eager_relation(self._owner, self._attr_name)
            if cached is not None:
                return cast("T", cached[0]) if cached else None
        owner_pk = getattr(self._owner, _pk_key(type(self._owner)))
        fk_col = getattr(self._related_model, self._fk)
        agg_col = getattr(self._related_model, self._column)
        pk_col = getattr(self._related_model, _pk_key(self._related_model))
        # Tiebreaker on the PK keeps "latest of many" deterministic when two rows
        # share the aggregate value.
        if self._aggregate == "max":
            order = (agg_col.desc(), pk_col.desc())
        else:
            order = (agg_col.asc(), pk_col.asc())
        stmt = select(self._related_model).where(fk_col == owner_pk).order_by(*order).limit(1)
        result = await get_active_session().execute(stmt)
        return result.scalars().first()


class HasOneOfMany(Generic[T]):
    """Descriptor for a has-one-of-many relation.

    Usage::

        class Post(Model):
            latest_comment: ClassVar[HasOneOfMany[Comment]] = HasOneOfMany(
                Comment, column="created_at", aggregate="max"
            )

    `foreign_key` defaults to ``{snake(owner)}_{local_key}``.
    """

    def __init__(
        self,
        related_model: type[T],
        *,
        foreign_key: str | None = None,
        local_key: str = "id",
        column: str = "created_at",
        aggregate: Aggregate = "max",
    ) -> None:
        self._related_model = related_model
        self._explicit_fk = foreign_key
        self._local_key = local_key
        self._column = column
        self._aggregate: Aggregate = aggregate
        self._attr_name: str | None = None
        self._owner_cls: type[Any] | None = None

    def __set_name__(self, owner: type[Any], name: str) -> None:
        self._attr_name = name
        self._owner_cls = owner

    @property
    def related_model(self) -> type[T]:
        return self._related_model

    def _foreign_key(self) -> str:
        if self._explicit_fk is not None:
            return self._explicit_fk
        if self._owner_cls is None:
            raise TypeError("HasOneOfMany used outside a class body")
        return f"{Str.snake(self._owner_cls.__name__)}_{self._local_key}"

    def link_spec(self) -> HasOneOfManyLink:
        owner = self._owner_cls
        if owner is None:
            raise TypeError("HasOneOfMany used outside a class body")
        return HasOneOfManyLink(
            related_model=self._related_model,
            foreign_key=self._foreign_key(),
            column=self._column,
            aggregate=self._aggregate,
            owner_pk_key=_pk_key(owner),
        )

    def __get__(
        self, obj: Any, objtype: type | None = None
    ) -> HasOneOfManyAccessor[T] | HasOneOfMany[T]:
        if obj is None:
            return self
        return HasOneOfManyAccessor(
            owner=obj,
            related_model=self._related_model,
            foreign_key=self._foreign_key(),
            column=self._column,
            aggregate=self._aggregate,
            attr_name=self._attr_name,
        )


async def batch_load_one_of_many(
    owners: list[Model],
    link: HasOneOfManyLink,
    attr_name: str,
) -> list[Any]:
    """Eager-load one-of-many for *owners* with a single grouped subquery.

    One ``SELECT fk, AGG(col) ... GROUP BY fk`` joined back to the related table,
    so we fetch ~one row per owner instead of every related row. Ties (two rows
    sharing the aggregate value) are broken by the larger PK, deterministically.
    """
    if not owners:
        return []
    related = link.related_model
    fk_col = getattr(related, link.foreign_key)
    agg_col = getattr(related, link.column)
    pk_key = _pk_key(related)
    owner_ids = [getattr(o, link.owner_pk_key) for o in owners]

    agg_func = sqla_func.max if link.aggregate == "max" else sqla_func.min
    agg_sub = (
        select(fk_col.label("ofm_fk"), agg_func(agg_col).label("ofm_agg"))
        .where(fk_col.in_(owner_ids))
        .group_by(fk_col)
        .subquery()
    )
    stmt = select(related).join(
        agg_sub, (fk_col == agg_sub.c.ofm_fk) & (agg_col == agg_sub.c.ofm_agg)
    )
    rows = (await get_active_session().execute(stmt)).scalars().all()

    # One winner per owner; on a tie keep the larger PK.
    winners: dict[Any, Any] = {}
    for row in rows:
        owner_key = getattr(row, link.foreign_key)
        current = winners.get(owner_key)
        if current is None or getattr(row, pk_key) > getattr(current, pk_key):
            winners[owner_key] = row

    flat: list[Any] = []
    for owner in owners:
        winner = winners.get(getattr(owner, link.owner_pk_key))
        set_eager_relation(owner, attr_name, [winner] if winner is not None else [])
        if winner is not None:
            flat.append(winner)
    return flat
