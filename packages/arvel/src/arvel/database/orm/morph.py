"""MorphOne and MorphMany — polymorphic relations using short class-name discriminators.

The ``{name}_type`` column stores the owner's unqualified class name
(e.g. ``"Post"``, not ``"app.models.Post"``).

Relations must be eager-loaded via ``.with_("relation")`` before accessing them
on a model instance. Accessing an un-loaded relation raises
:class:`LazyLoadingError` immediately — there is no implicit DB hit on
attribute access, matching Laravel's strict-mode behaviour.

Pattern::

    products = await Product.with_("media").all()
    for product in products:
        imgs = product.media          # list[Media] — sync, no await
        first = product.media[0]      # direct indexing
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast, overload

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.orm import Mapper

from arvel.database.orm._eager import (
    clear_eager_relation,
    get_eager_relation,
    set_eager_relation,
)
from arvel.database.orm.morph_map import get_morph_alias, resolve_morph_class
from arvel.database.session import autocommit, get_active_session

if TYPE_CHECKING:
    from arvel.database.model import Model

T = TypeVar("T")


class LazyLoadingError(AttributeError):
    """Raised when a relation is accessed without prior eager loading.

    Use ``.with_("relation_name")`` on the query builder before fetching.
    """


@dataclass(frozen=True)
class MorphChildLink:
    """Resolved metadata for a MorphOne/MorphMany, used by the query builder.

    ``owner_type`` is the owning model's morph alias; ``single`` is True for
    MorphOne (cardinality only matters to the query builder, not the descriptor).
    """

    related_model: type[Any]
    name: str
    owner_type: str
    single: bool


def _morph_id_coercer(id_col: Any) -> Callable[[Any], Any]:
    """Return a function that casts an owner key to the morph id column's type.

    String id columns get ``str()``; everything else passes through unchanged.
    """
    from sqlalchemy import String

    is_string = isinstance(getattr(id_col, "type", None), String)
    return str if is_string else (lambda v: v)


# ── MorphOne ──────────────────────────────────────────────────────────────────


class MorphOne(Generic[T]):
    """Descriptor for a polymorphic one-to-one relation.

    Access after eager loading is sync::

        class Post(Model):
            image: MorphOne[Image] = MorphOne(Image, name="imageable")

        post = await Post.with_("image").first()
        img: Image | None = post.image   # sync, no await
    """

    def __init__(self, related_model: type[T], *, name: str) -> None:
        self._related_model = related_model
        self._name = name
        self._attr_name: str | None = None

    def __set_name__(self, owner: type[Any], name: str) -> None:
        self._attr_name = name

    @property
    def related_model(self) -> type[T]:
        return self._related_model

    @property
    def name(self) -> str:
        return self._name

    def link_spec(self, owner_type: str) -> MorphChildLink:
        return MorphChildLink(
            related_model=self._related_model, name=self._name, owner_type=owner_type, single=True
        )

    @overload
    def __get__(self, obj: None, objtype: type) -> MorphOne[T]: ...

    @overload
    def __get__(self, obj: object, objtype: type | None) -> T | None: ...

    def __get__(self, obj: object | None, objtype: type | None = None) -> T | None | MorphOne[T]:
        if obj is None:
            return self
        if self._attr_name is None:
            raise LazyLoadingError(
                f"MorphOne descriptor was not assigned to a class attribute "
                f"on {type(obj).__name__!r}."
            )
        cached = get_eager_relation(obj, self._attr_name)
        if cached is None:
            raise LazyLoadingError(
                f"Relation {self._attr_name!r} on {type(obj).__name__!r} is not loaded. "
                f"Use .with_({self._attr_name!r}) on the query builder."
            )
        return cast("T", cached[0]) if cached else None


# ── MorphMany ─────────────────────────────────────────────────────────────────


class MorphMany(Generic[T]):
    """Descriptor for a polymorphic one-to-many relation.

    Access after eager loading is sync::

        class Post(Model):
            comments: MorphMany[Comment] = MorphMany(Comment, name="commentable")

        post = await Post.with_("comments").first()
        all_comments: list[Comment] = post.comments   # sync, no await
    """

    def __init__(self, related_model: type[T], *, name: str) -> None:
        self._related_model = related_model
        self._name = name
        self._attr_name: str | None = None

    def __set_name__(self, owner: type[Any], name: str) -> None:
        self._attr_name = name

    @property
    def related_model(self) -> type[T]:
        return self._related_model

    @property
    def name(self) -> str:
        return self._name

    def link_spec(self, owner_type: str) -> MorphChildLink:
        return MorphChildLink(
            related_model=self._related_model, name=self._name, owner_type=owner_type, single=False
        )

    @overload
    def __get__(self, obj: None, objtype: type) -> MorphMany[T]: ...

    @overload
    def __get__(self, obj: object, objtype: type | None) -> list[T]: ...

    def __get__(self, obj: object | None, objtype: type | None = None) -> list[T] | MorphMany[T]:
        if obj is None:
            return self
        if self._attr_name is None:
            raise LazyLoadingError(
                f"MorphMany descriptor was not assigned to a class attribute "
                f"on {type(obj).__name__!r}."
            )
        cached = get_eager_relation(obj, self._attr_name)
        if cached is None:
            raise LazyLoadingError(
                f"Relation {self._attr_name!r} on {type(obj).__name__!r} is not loaded. "
                f"Use .with_({self._attr_name!r}) on the query builder."
            )
        return [cast("T", row) for row in cached]


# ── MorphTo (inverse) ───────────────────────────────────────────────────────


def _parent_pk_column(parent_cls: type[Any]) -> Any:
    mapper: Mapper[Any] = cast("Mapper[Any]", sa_inspect(parent_cls))
    return mapper.primary_key[0]


def _parent_pk_key(parent_cls: type[Any]) -> str:
    key = _parent_pk_column(parent_cls).key
    if key is None:
        raise TypeError(f"{parent_cls.__name__} primary key column has no key")
    return cast("str", key)


class MorphToAccessor(Generic[T]):
    """Accessor for a child's polymorphic parent — ``comment.commentable``.

    Awaitable: ``parent = await comment.commentable``. Resolves the parent class
    from the stored ``{name}_type`` token (via the morph map) and loads it by
    ``{name}_id``. Reads the eager cache when the relation was batch-loaded.
    """

    def __init__(self, owner: Any, name: str, attr_name: str | None) -> None:
        self._owner = owner
        self._name = name
        self._attr_name = attr_name

    def __await__(self) -> Generator[Any, None, T | None]:
        return self.query().__await__()

    @autocommit(write=False)
    async def query(self) -> T | None:
        if self._attr_name is not None:
            cached = get_eager_relation(self._owner, self._attr_name)
            if cached is not None:
                return cast("T", cached[0]) if cached else None
        type_token = getattr(self._owner, f"{self._name}_type", None)
        id_val = getattr(self._owner, f"{self._name}_id", None)
        if type_token is None or id_val is None:
            return None
        parent_cls = resolve_morph_class(type_token)
        stmt = select(parent_cls).where(_parent_pk_column(parent_cls) == id_val).limit(1)
        result = await get_active_session().execute(stmt)
        return cast("T | None", result.scalars().first())

    def associate(self, model: Model) -> Any:
        """Point this child at ``model``: set ``{name}_type`` + ``{name}_id`` together."""
        setattr(self._owner, f"{self._name}_type", get_morph_alias(type(model)))
        setattr(self._owner, f"{self._name}_id", model.get_key())
        if self._attr_name is not None:
            set_eager_relation(self._owner, self._attr_name, [model])
        return self._owner

    def dissociate(self) -> Any:
        """Clear the polymorphic parent: null both discriminator columns."""
        setattr(self._owner, f"{self._name}_type", None)
        setattr(self._owner, f"{self._name}_id", None)
        if self._attr_name is not None:
            clear_eager_relation(self._owner, self._attr_name)
        return self._owner


class MorphTo(Generic[T]):
    """Descriptor for the inverse polymorphic relation (child → parent).

    Usage::

        class Comment(Model):
            commentable: MorphTo[Any] = MorphTo(name="commentable")
    """

    def __init__(self, *, name: str) -> None:
        self._name = name
        self._attr_name: str | None = None

    def __set_name__(self, owner: type[Any], name: str) -> None:
        self._attr_name = name

    @property
    def name(self) -> str:
        return self._name

    def __get__(self, obj: Any, objtype: type | None = None) -> MorphToAccessor[T] | MorphTo[T]:
        if obj is None:
            return self
        return MorphToAccessor(owner=obj, name=self._name, attr_name=self._attr_name)


async def batch_load_morph_to(children: list[Any], name: str, attr_name: str) -> None:
    """Eager-load the polymorphic parent for *children*, one query per distinct type.

    Groups children by their ``{name}_type`` token, resolves each token to a parent
    class via the morph map, and loads that group's parents in a single
    ``WHERE pk IN (...)``. Stores each parent on its child via the eager cache.
    """
    by_type: dict[str, list[Any]] = {}
    for child in children:
        token = getattr(child, f"{name}_type", None)
        cid = getattr(child, f"{name}_id", None)
        if token is None or cid is None:
            set_eager_relation(child, attr_name, [])
            continue
        by_type.setdefault(token, []).append(child)

    session = get_active_session()
    for token, group in by_type.items():
        parent_cls = resolve_morph_class(token)
        pk_key = _parent_pk_key(parent_cls)
        ids = {getattr(c, f"{name}_id") for c in group}
        stmt = select(parent_cls).where(_parent_pk_column(parent_cls).in_(ids))
        rows = (await session.execute(stmt)).scalars().all()
        index = {getattr(r, pk_key): r for r in rows}
        for child in group:
            parent = index.get(getattr(child, f"{name}_id"))
            set_eager_relation(child, attr_name, [parent] if parent is not None else [])


async def batch_load_morph_children(
    owners: list[Model],
    link: MorphChildLink,
    attr_name: str,
    where: Any | None = None,
) -> list[Any]:
    """Eager-load MorphOne/MorphMany children for *owners* in a single query.

    One ``WHERE {name}_type = owner_alias AND {name}_id IN (owner_pks)``, grouped
    back to each owner via the eager cache. ``where`` is an optional extra
    predicate from a constraint closure.
    """
    if not owners:
        return []
    owner_mapper: Mapper[Any] = cast("Mapper[Any]", sa_inspect(type(owners[0])))
    owner_pk_key = owner_mapper.primary_key[0].key
    if owner_pk_key is None:
        raise TypeError(f"{type(owners[0]).__name__} primary key column has no key")

    related = link.related_model
    type_col = getattr(related, f"{link.name}_type")
    id_col = getattr(related, f"{link.name}_id")
    # The morph id column may be a string (some tables store keys as strings to
    # carry both int and UUID parents) while the owner's PK is an int. Coerce
    # owner keys to the column's type so both the IN-filter and the regrouping
    # below line up with what's actually stored.
    coerce = _morph_id_coercer(id_col)
    owner_ids = [coerce(getattr(o, owner_pk_key)) for o in owners]
    stmt = select(related).where(type_col == link.owner_type).where(id_col.in_(owner_ids))
    if where is not None:
        stmt = stmt.where(where)

    rows = (await get_active_session().execute(stmt)).scalars().all()
    grouped: dict[Any, list[Any]] = {}
    for row in rows:
        grouped.setdefault(getattr(row, f"{link.name}_id"), []).append(row)

    flat: list[Any] = []
    for owner in owners:
        children = grouped.get(coerce(getattr(owner, owner_pk_key)), [])
        set_eager_relation(owner, attr_name, children)
        flat.extend(children)
    return flat
