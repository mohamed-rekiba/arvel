"""``ModelCollection`` — a ``Collection`` of Arvent model instances.

Returned by ``QueryBuilder.all()``/``get()`` for model rows. Adds the PK-aware
and relation-aware helpers that belong on a model-row collection: batch ``load``,
``model_keys``, key-based ``find``/``contains``/``only``/``except_``/``diff``/``intersect``,
``to_query``, ``fresh``, and ``make_hidden``/``make_visible``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from arvel.support.collections import Collection

if TYPE_CHECKING:
    from arvel.database.model import Model
    from arvel.database.query import QueryBuilder

T = TypeVar("T", bound="Model")


class ModelCollection(Collection[T]):
    """A ``Collection`` of mapped model instances with PK- and relation-aware helpers."""

    def _model(self) -> type[T]:
        if not self:
            raise ValueError("Cannot infer the model type from an empty collection.")
        return type(self[0])

    def model_keys(self) -> list[Any]:
        """Primary keys of every member, in order."""
        return [m.get_key() for m in self]

    async def load(self, *relations: str) -> ModelCollection[T]:
        """Batch-load *relations* onto every member in as few queries as possible."""
        if not self:
            return self
        from arvel.database.query import (
            is_async_relation,
            load_async_relation_path,
            validate_relation_head,
        )

        model = self._model()
        # Fail loud on typos, same as QueryBuilder.with_(), instead of a silent no-op.
        for rel in relations:
            validate_relation_head(model, rel)
        async_rels = [r for r in relations if is_async_relation(model, r)]
        sa_rels = [r for r in relations if r not in async_rels]
        for rel in async_rels:
            await load_async_relation_path(model, list(self), rel, None)
        if sa_rels:
            await self._load_sa(sa_rels)
        return self

    async def load_missing(self, *relations: str) -> ModelCollection[T]:
        """Load only the relations not already populated on at least one member."""
        from sqlalchemy import inspect as sqla_inspect

        from arvel.database.orm._eager import get_eager_relation
        from arvel.database.query import is_async_relation, validate_relation_head

        model = self._model()
        missing: list[str] = []
        for rel in relations:
            validate_relation_head(model, rel)
            head = rel.partition(".")[0]
            # Async descriptor relations live in the eager cache, never in SA's
            # `unloaded`; check the cache so e.g. load_missing("roles") isn't a no-op.
            if is_async_relation(model, rel):
                if any(get_eager_relation(m, head) is None for m in self):
                    missing.append(rel)
            elif any(head in sqla_inspect(m).unloaded for m in self):
                missing.append(rel)
        if missing:
            await self.load(*missing)
        return self

    async def _load_sa(self, sa_rels: list[str]) -> None:
        from sqlalchemy import inspect as sqla_inspect
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from arvel.database.session import session_scope

        model = self._model()
        mapper = sqla_inspect(model)
        pk_col = mapper.primary_key[0]
        keys = self.model_keys()
        async with session_scope(commit=False) as session:
            # Expire just the requested relations so selectinload replaces them even
            # under expire_on_commit=False; leave loaded column values intact.
            for member in self:
                state = sqla_inspect(member)
                if state.detached:
                    session.add(member)
                session.expire(member, sa_rels)
            stmt = select(model).where(pk_col.in_(keys))
            for rel in sa_rels:
                attr = getattr(model, rel, None)
                if attr is not None:
                    stmt = stmt.options(selectinload(attr))
            result = await session.execute(stmt)
            by_key = {fresh.get_key(): fresh for fresh in result.scalars().all()}
            for member in self:
                fresh = by_key.get(member.get_key())
                if fresh is None:
                    continue
                for rel in sa_rels:
                    loaded = getattr(fresh, rel, None)
                    if loaded is not None:
                        object.__setattr__(member, rel, loaded)

    def find(self, key: Any) -> T | None:
        """Return the member whose primary key matches *key* (or a model's key)."""
        target = key.get_key() if hasattr(key, "get_key") else key
        for member in self:
            if member.get_key() == target:
                return member
        return None

    def contains(self, fn_or_value: Any) -> bool:
        """PK-aware membership: a callable predicate, a model instance, or a raw key."""
        if callable(fn_or_value):
            return any(fn_or_value(member) for member in self)
        return self.find(fn_or_value) is not None

    def only(self, *keys: Any) -> ModelCollection[T]:
        """Members whose primary key is in *keys*."""
        wanted = set(keys)
        return ModelCollection(m for m in self if m.get_key() in wanted)

    def except_(self, *keys: Any) -> ModelCollection[T]:
        """Members whose primary key is not in *keys*."""
        unwanted = set(keys)
        return ModelCollection(m for m in self if m.get_key() not in unwanted)

    def diff(self, other: list[T]) -> ModelCollection[T]:
        """Members not present (by primary key) in *other*."""
        other_keys = {m.get_key() for m in other}
        return ModelCollection(m for m in self if m.get_key() not in other_keys)

    def intersect(self, other: list[T]) -> ModelCollection[T]:
        """Members also present (by primary key) in *other*."""
        other_keys = {m.get_key() for m in other}
        return ModelCollection(m for m in self if m.get_key() in other_keys)

    def to_query(self) -> QueryBuilder[T]:
        """A query scoped to the members' primary keys (``WHERE pk IN (...)``)."""
        from sqlalchemy import inspect as sqla_inspect

        if not self:
            raise ValueError("Cannot build a query from an empty collection.")
        model = self._model()
        pk_col = sqla_inspect(model).primary_key[0]
        return model.query().where(pk_col.in_(self.model_keys()))

    async def fresh(self, *relations: str) -> ModelCollection[T]:
        """Re-fetch every member from the database, preserving order, dropping deleted rows."""
        if not self:
            return ModelCollection()
        from sqlalchemy import inspect as sqla_inspect

        from arvel.database.session import session_scope

        model = self._model()
        pk_col = sqla_inspect(model).primary_key[0]
        ordered_keys = self.model_keys()

        async with session_scope(commit=False):
            # Bulk writes bypass the identity map; expire so the re-query reads DB values.
            for member in self:
                state = sqla_inspect(member)
                if not state.detached:
                    member_session = state.session
                    if member_session is not None:
                        member_session.expire(member)

            qb = model.query().where(pk_col.in_(ordered_keys))
            for rel in relations:
                qb = qb.with_(rel)
            reloaded = await qb.get()
        by_key = {m.get_key(): m for m in reloaded}
        return ModelCollection(by_key[k] for k in ordered_keys if k in by_key)

    def make_hidden(self, *fields: str) -> ModelCollection[T]:
        """Hide *fields* on every member's serialization."""
        for member in self:
            member.make_hidden(*fields)
        return self

    def make_visible(self, *fields: str) -> ModelCollection[T]:
        """Unhide *fields* on every member's serialization."""
        for member in self:
            member.make_visible(*fields)
        return self


__all__ = ["ModelCollection"]
