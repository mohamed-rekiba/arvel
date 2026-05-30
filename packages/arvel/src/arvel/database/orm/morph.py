"""MorphOne and MorphMany — polymorphic relations using short class-name discriminators.

ADR-022: the ``{name}_type`` column stores the owner's unqualified class name
(e.g. ``"Post"``, not ``"app.models.Post"``).
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, Generic, TypeVar

from sqlalchemy import select

from arvel.database.session import get_active_session

T = TypeVar("T")


# ── MorphOne ──────────────────────────────────────────────────────────────────


class MorphOneAccessor(Generic[T]):
    """Accessor returned when accessing a MorphOne descriptor on an instance.

    Awaitable: ``result = await post.image``
    Creates: ``img = await post.image.create(url=...)``
    """

    def __init__(self, owner: Any, related_model: type[T], name: str) -> None:
        self._owner = owner
        self._related_model = related_model
        self._name = name  # morph base name, e.g. "imageable"

    # ── awaitable protocol ──────────────────────────────────────────────────

    def __await__(self) -> Generator[Any, None, T | None]:
        return self.query().__await__()

    async def query(self) -> T | None:
        session = get_active_session()
        type_col = getattr(self._related_model, f"{self._name}_type")
        id_col = getattr(self._related_model, f"{self._name}_id")
        owner_type = type(self._owner).__name__  # short name per ADR-022
        stmt = (
            select(self._related_model)
            .where(type_col == owner_type)
            .where(id_col == self._owner.id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    # ── factory ─────────────────────────────────────────────────────────────

    async def create(self, **attrs: Any) -> T:
        """Create a related row with discriminator columns set automatically."""
        attrs[f"{self._name}_type"] = type(self._owner).__name__
        attrs[f"{self._name}_id"] = self._owner.id
        model: Any = self._related_model
        return await model.create(**attrs)  # type: ignore[no-any-return]


class MorphOne(Generic[T]):
    """Descriptor for a polymorphic one-to-one relation.

    Usage::

        class Post(Model):
            image: MorphOne[Image] = MorphOne(Image, name="imageable")
    """

    def __init__(self, related_model: type[T], *, name: str) -> None:
        self._related_model = related_model
        self._name = name

    def __get__(self, obj: Any, objtype: type | None = None) -> MorphOneAccessor[T] | MorphOne[T]:
        if obj is None:
            return self
        return MorphOneAccessor(owner=obj, related_model=self._related_model, name=self._name)


# ── MorphMany ─────────────────────────────────────────────────────────────────


class MorphManyAccessor(Generic[T]):
    """Accessor returned when accessing a MorphMany descriptor on an instance."""

    def __init__(self, owner: Any, related_model: type[T], name: str) -> None:
        self._owner = owner
        self._related_model = related_model
        self._name = name

    async def all(self) -> list[T]:
        """Return all related rows for this owner."""
        session = get_active_session()
        type_col = getattr(self._related_model, f"{self._name}_type")
        id_col = getattr(self._related_model, f"{self._name}_id")
        owner_type = type(self._owner).__name__
        stmt = (
            select(self._related_model)
            .where(type_col == owner_type)
            .where(id_col == self._owner.id)
        )
        result = await session.execute(stmt)
        return list(result.scalars())

    async def create(self, **attrs: Any) -> T:
        """Create a related row with discriminator columns set automatically."""
        attrs[f"{self._name}_type"] = type(self._owner).__name__
        attrs[f"{self._name}_id"] = self._owner.id
        model: Any = self._related_model
        return await model.create(**attrs)  # type: ignore[no-any-return]


class MorphMany(Generic[T]):
    """Descriptor for a polymorphic one-to-many relation.

    Usage::

        class Post(Model):
            comments: MorphMany[Comment] = MorphMany(Comment, name="commentable")
    """

    def __init__(self, related_model: type[T], *, name: str) -> None:
        self._related_model = related_model
        self._name = name

    def __get__(self, obj: Any, objtype: type | None = None) -> MorphManyAccessor[T] | MorphMany[T]:
        if obj is None:
            return self
        return MorphManyAccessor(owner=obj, related_model=self._related_model, name=self._name)
