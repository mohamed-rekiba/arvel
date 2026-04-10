"""Polymorphic (morph) relationship helpers.

Implements ``morph_to``, ``morph_many``, and ``morph_to_many`` — the
pattern where a model can belong to multiple parent types via a
``{name}_type`` / ``{name}_id`` column pair.

Unlike standard SA relationships, polymorphic relationships are resolved
at runtime by querying with the type discriminator. SA's ``relationship()``
isn't used for morph relationships; instead, resolution happens via
explicit queries in ``load_morph_parent`` and ``query_morph_children``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from arvel.data.model import ArvelModel

# Global morph type map: {alias: model_class}
_MORPH_TYPE_MAP: dict[str, type[ArvelModel]] = {}


def register_morph_type(alias: str, model_cls: type[ArvelModel]) -> None:
    """Register a short alias for a model class in the morph type map."""
    _MORPH_TYPE_MAP[alias] = model_cls


def get_morph_type_map() -> dict[str, type[ArvelModel]]:
    """Return the current morph type map."""
    return dict(_MORPH_TYPE_MAP)


def resolve_morph_type(type_value: str) -> type[ArvelModel]:
    """Resolve a morph type string to a model class.

    Checks the morph type map first, then falls back to the full
    class path. Raises ValueError if the type cannot be resolved.
    """
    if type_value in _MORPH_TYPE_MAP:
        return _MORPH_TYPE_MAP[type_value]

    msg = (
        f"Unknown morph type: {type_value!r}. "
        f"Register it with register_morph_type() or add it to the model's morph_map."
    )
    raise ValueError(msg)


def morph_alias(model_cls: type[ArvelModel]) -> str:
    """Get the morph alias for a model class (reverse lookup)."""
    for alias, cls in _MORPH_TYPE_MAP.items():
        if cls is model_cls:
            return alias
    return model_cls.__name__


@dataclass(frozen=True)
class MorphDescriptor:
    """Metadata about a polymorphic relationship declaration."""

    morph_name: str
    morph_type: str  # "morph_to", "morph_many", "morph_to_many"
    related_model: type[ArvelModel] | None = None
    morph_map: dict[str, type[ArvelModel]] = field(default_factory=dict)


def morph_to(name: str) -> MorphDescriptor:
    """Declare the child side of a polymorphic relationship.

    The model must have ``{name}_type`` and ``{name}_id`` columns.

    Example::

        class Comment(ArvelModel):
            commentable_type: Mapped[str] = mapped_column(String(100))
            commentable_id: Mapped[int] = mapped_column()
            commentable = morph_to("commentable")
    """
    return MorphDescriptor(morph_name=name, morph_type="morph_to")


def morph_many(related: type[ArvelModel], name: str) -> MorphDescriptor:
    """Declare the parent side of a polymorphic one-to-many relationship.

    Example::

        class Post(ArvelModel):
            comments = morph_many(Comment, "commentable")
    """
    return MorphDescriptor(morph_name=name, morph_type="morph_many", related_model=related)


def morph_to_many(
    related: type[ArvelModel],
    name: str,
    *,
    morph_map: dict[str, type[ArvelModel]] | None = None,
) -> MorphDescriptor:
    """Declare a polymorphic many-to-many relationship via a pivot table.

    Example::

        class Post(ArvelModel):
            tags = morph_to_many(Tag, "taggable")
    """
    return MorphDescriptor(
        morph_name=name,
        morph_type="morph_to_many",
        related_model=related,
        morph_map=morph_map or {},
    )


async def load_morph_parent(
    instance: ArvelModel,
    name: str,
    session: AsyncSession,
) -> ArvelModel | None:
    """Eagerly load the polymorphic parent for a morph_to relationship.

    Reads ``{name}_type`` and ``{name}_id`` from the instance, resolves
    the parent model class via the morph type map, and queries for it.
    """
    type_col = f"{name}_type"
    id_col = f"{name}_id"

    type_value = getattr(instance, type_col, None)
    id_value = getattr(instance, id_col, None)

    if type_value is None or id_value is None:
        return None

    parent_cls = resolve_morph_type(type_value)
    # AsyncSession.get() keeps the model type and avoids untyped scalar extraction.
    return await session.get(parent_cls, id_value)


async def query_morph_children(
    parent: ArvelModel,
    related_cls: type[ArvelModel],
    name: str,
    session: AsyncSession,
) -> list[ArvelModel]:
    """Query all children of a polymorphic one-to-many relationship.

    Filters ``{name}_type`` to the parent's morph alias and
    ``{name}_id`` to the parent's PK.
    """
    from sqlalchemy import select

    parent_cls = type(parent)
    alias = morph_alias(parent_cls)
    pk_value = _get_pk_value(parent)

    type_col = getattr(related_cls, f"{name}_type", None)
    id_col_attr = getattr(related_cls, f"{name}_id", None)

    if type_col is None or id_col_attr is None:
        msg = (
            f"{related_cls.__name__} must have '{name}_type' and '{name}_id' "
            f"columns for morph_many relationship"
        )
        raise ValueError(msg)

    stmt = select(related_cls).where(type_col == alias, id_col_attr == pk_value)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _get_pk_value(instance: ArvelModel) -> int | str:
    """Get the primary key value from a model instance."""
    table = getattr(type(instance), "__table__", None)
    if table is not None:
        for col in table.columns:
            if col.primary_key:
                return getattr(instance, col.name)  # type: ignore[no-any-return]
    msg = f"No primary key found on {type(instance).__name__}"
    raise ValueError(msg)
