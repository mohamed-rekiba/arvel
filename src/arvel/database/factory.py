"""arvel.database.factory — model factories (Laravel-style) for tests and seeders.

Subclass :class:`Factory`, set ``model``, and implement ``definition()``::

    class UserFactory(Factory[User]):
        model = User

        def definition(self) -> dict[str, Any]:
            return {"name": self.faker.name(), "email": self.faker.unique.email()}

Then ``UserFactory().make()`` (unsaved) / ``await UserFactory().create()`` (persisted) for one, or the
fluent batch ``await UserFactory().count(3).create()`` for many. ``state()`` layers attribute overrides
(dict or ``callable(attrs) -> dict``), ``sequence()`` cycles values across a batch, and ``raw()`` returns
the attribute dict without a model. ``self.faker`` is a lazily-created Faker (the ``faker`` dev package).
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from arvel.database.model import Model

# `<Model>` -> the `Factory` subclass registered for it (`Model.factory()`'s convention lookup).
# Populated automatically as `Factory` subclasses are defined/imported — see `__init_subclass__`.
_FACTORY_REGISTRY: dict[type, type[Factory[Any]]] = {}


def factory_for(model: type[Any]) -> Factory[Any]:
    """Resolve ``model``'s registered factory (Laravel ``Model::factory()``'s convention lookup).
    Raises ``LookupError`` with an actionable message when nothing is registered — either the
    ``<Model>Factory`` module was never imported, or the model needs an explicit ``__factory__``."""
    factory_cls = _FACTORY_REGISTRY.get(model)
    if factory_cls is None:
        raise LookupError(
            f"no Factory registered for {model.__name__}. Define a `{model.__name__}Factory"
            f"(Factory[{model.__name__}])` with `model = {model.__name__}` (and make sure it's "
            f"imported), or set `{model.__name__}.__factory__` explicitly."
        )
    return factory_cls()


class Factory[M: Model]:
    """Base model factory. Define ``model`` + ``definition()`` on a subclass."""

    model: type[M]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # only a concrete factory (one that actually names a model) registers — an intermediate
        # abstract base in an app's factory hierarchy has no `model` of its own to collide on
        target = getattr(cls, "model", None)
        if target is not None:
            _FACTORY_REGISTRY.setdefault(target, cls)

    def __init__(self) -> None:
        self._states: list[dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]]] = []
        self._sequence: list[dict[str, Any]] = []
        self._after_making: list[Callable[[M], Any]] = []
        self._after_creating: list[Callable[[M], Any]] = []
        self._for: list[tuple[Factory[Any] | Model, str, str | None]] = []
        self._has: list[tuple[Factory[Any], str, int, str | None]] = []
        self._recycled: dict[type, list[Model]] = {}

    @property
    def faker(self) -> Any:
        """A lazily-created, memoized ``Faker`` instance (requires the ``faker`` package)."""
        faker = getattr(self, "_faker", None)
        if faker is None:
            from faker import Faker

            faker = Faker()
            self._faker = faker
        return faker

    def definition(self) -> dict[str, Any]:
        """Return the default attribute dict for one model. Override on the subclass."""
        raise NotImplementedError

    def state(
        self, overrides: dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]]
    ) -> Factory[M]:
        """A copy of this factory with an extra state layer — a dict, or a ``callable(attrs) -> dict``
        computed from the attributes so far (Laravel ``state``). Composable."""
        clone = copy.copy(self)
        clone._states = [*self._states, overrides]
        return clone

    def sequence(self, *items: dict[str, Any]) -> Factory[M]:
        """A copy of this factory that cycles ``items`` across a batch (Laravel ``sequence``)."""
        clone = copy.copy(self)
        clone._sequence = list(items)
        return clone

    def after_making(self, callback: Callable[[M], Any]) -> Factory[M]:
        """A copy of this factory that also runs ``callback(instance)`` right after each instance is
        built — before it's persisted (Laravel ``afterMaking``). Runs for both ``make`` and
        ``create``, in the order registered; ``callback`` may be sync or async."""
        clone = copy.copy(self)
        clone._after_making = [*self._after_making, callback]
        return clone

    def after_creating(self, callback: Callable[[M], Any]) -> Factory[M]:
        """A copy of this factory that also runs ``callback(instance)`` right after each instance is
        persisted (Laravel ``afterCreating``) — ``create``/``create_many`` only. Ordered with any
        other ``after_creating`` callbacks; ``callback`` may be sync or async."""
        clone = copy.copy(self)
        clone._after_creating = [*self._after_creating, callback]
        return clone

    def for_(
        self, parent: Factory[Any] | Model, relation: str, *, foreign_key: str | None = None
    ) -> Factory[M]:
        """A copy of this factory that sets the **belongs-to** ``relation`` on every created
        instance (Laravel ``for``): ``parent`` is created once (or reused via :meth:`recycle`) and
        its owner key is written to the child's foreign key — derived from ``relation`` (a method on
        this factory's model, e.g. ``def user(self): return self.belongs_to(User)``), or
        ``foreign_key`` to override. An explicit keyword to ``create()``/``make()`` still wins."""
        clone = copy.copy(self)
        clone._for = [*self._for, (parent, relation, foreign_key)]
        return clone

    def has(
        self,
        related: Factory[Any] | FactoryBatch[Any],
        relation: str,
        count: int = 1,
        *,
        foreign_key: str | None = None,
    ) -> Factory[M]:
        """A copy of this factory that, after creating the parent, also creates ``count`` ``related``
        rows with their foreign key set to the parent (Laravel ``has``) — derived from ``relation``
        (a method on the *parent* model, e.g. ``def posts(self): return self.has_many(Post)``), or
        ``foreign_key`` to override. ``related`` may be a bare factory (paired with ``count``) or a
        ``count()`` batch (``has(Post.factory().count(2), "posts")``) — its count then wins. Only
        wired on ``create``/``create_many`` (there's no parent row to point at from ``make``)."""
        factory, resolved_count = (
            (related.factory, related.count)
            if isinstance(related, FactoryBatch)
            else (related, count)
        )
        clone = copy.copy(self)
        clone._has = [*self._has, (factory, relation, resolved_count, foreign_key)]
        return clone

    def recycle(self, instances: Model | Sequence[Model]) -> Factory[M]:
        """A copy of this factory that reuses ``instances`` for any :meth:`for_` needing that model
        class, instead of creating a new parent each time (Laravel ``recycle``)."""
        from arvel.database.model import Model as ModelBase

        pool = {key: list(value) for key, value in self._recycled.items()}
        items: list[Model] = [instances] if isinstance(instances, ModelBase) else list(instances)
        for item in items:
            pool.setdefault(type(item), []).append(item)
        clone = copy.copy(self)
        clone._recycled = pool
        return clone

    def _attributes(self, overrides: dict[str, Any], index: int = 0) -> dict[str, Any]:
        # order (later wins): definition() → states → sequence[index] → overrides — so a callable
        # state never sees its own sequence value (sequence applies after states)
        attrs = self.definition()
        for state in self._states:
            extra = state(attrs) if callable(state) else state
            attrs = {**attrs, **extra}
        if self._sequence:
            attrs = {**attrs, **self._sequence[index % len(self._sequence)]}
        return {**attrs, **overrides}

    def raw(self, **overrides: Any) -> dict[str, Any]:
        """The resolved attribute dict for one model — no instance built (Laravel ``raw``)."""
        return self._attributes(overrides)

    async def _run_hook(self, callback: Callable[[M], Any], instance: M) -> None:
        import inspect

        result = callback(instance)
        if inspect.isawaitable(result):
            await result

    async def _resolve_parent(self, spec: Factory[Any] | Model) -> Any:
        # `Any`, not `Model`: reads the resolved parent's `_attributes` right after (like every
        # relation in relations.py does on `self.parent`) — internal, cross-class, same package.
        from arvel.database.model import Model as ModelBase

        if isinstance(spec, ModelBase):
            return spec
        recycled = self._recycled.get(spec.model)
        # ponytail: always the first recycled instance, not a round-robin/random pick — the one
        # documented use case (reuse a single instance) doesn't need more; revisit if a test needs
        # `recycle([a, b])` to distribute across creates.
        return recycled[0] if recycled else await spec.create()

    async def _resolve_for(
        self, attrs: dict[str, Any], overrides: dict[str, Any]
    ) -> dict[str, Any]:
        if not self._for:
            return attrs
        resolved = dict(attrs)
        bare = self.model()  # unsaved — only used to introspect the relation's FK convention
        for parent_spec, relation, foreign_key in self._for:
            rel = getattr(bare, relation)()
            fk = foreign_key or rel.foreign_key
            if fk in overrides:  # an explicit override always wins over the derived FK
                continue
            parent = await self._resolve_parent(parent_spec)
            resolved[fk] = parent._attributes.get(rel.owner_key)
        return resolved

    async def _resolve_has(self, parent: Any) -> None:
        for related_factory, relation, count, foreign_key in self._has:
            rel = getattr(parent, relation)()
            fk = foreign_key or rel.foreign_key
            value = parent._attributes.get(rel.local_key)
            if count == 1:
                await related_factory.create(**{fk: value})
            else:
                await related_factory.count(count).create(**{fk: value})

    def make(self, **overrides: Any) -> M:
        """Build one unsaved model instance. ``after_making`` callbacks run here too, but must be
        **sync** — an async callback only actually runs (awaited) via ``create``/``create_many``."""
        instance = self.model(**self._attributes(overrides))
        for callback in self._after_making:
            callback(instance)
        return instance

    async def create(self, **overrides: Any) -> M:
        """Build and persist one model instance (running any ``for_``/``after_making``/
        ``after_creating``/``has`` wired onto this factory)."""
        return await self._create_one(overrides, 0)

    def make_many(self, count: int, **overrides: Any) -> list[M]:
        """Build ``count`` unsaved instances (sequence applied per index)."""
        return [self.model(**self._attributes(overrides, i)) for i in range(count)]

    async def create_many(self, count: int, **overrides: Any) -> list[M]:
        """Build and persist ``count`` instances (sequence applied per index)."""
        return [await self._create_one(overrides, i) for i in range(count)]

    async def _create_one(self, overrides: dict[str, Any], index: int) -> M:
        attrs = self._attributes(overrides, index)
        attrs = await self._resolve_for(attrs, overrides)
        instance = self.model()
        instance.fill(attrs)
        for callback in self._after_making:
            await self._run_hook(callback, instance)
        await instance.save()
        for callback in self._after_creating:
            await self._run_hook(callback, instance)
        await self._resolve_has(instance)
        return instance

    def count(self, count: int) -> FactoryBatch[M]:
        """Begin a fluent batch — ``factory().count(3).create()`` (Laravel ``count``)."""
        return FactoryBatch(self, count)


class FactoryBatch[M: Model]:
    """A fluent ``count``-bound batch whose ``make``/``create`` return lists. ``state``/``sequence``
    keep chaining (they re-wrap the underlying factory)."""

    def __init__(self, factory: Factory[M], count: int) -> None:
        self._factory = factory
        self._count = count

    @property
    def factory(self) -> Factory[M]:
        """The wrapped factory — read by ``Factory.has()`` when given a batch instead of a bare
        factory (``has(Post.factory().count(2), "posts")``)."""
        return self._factory

    @property
    def count(self) -> int:
        """The batch size — read by ``Factory.has()`` (see :attr:`factory`)."""
        return self._count

    def state(
        self, overrides: dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]]
    ) -> FactoryBatch[M]:
        return FactoryBatch(self._factory.state(overrides), self._count)

    def sequence(self, *items: dict[str, Any]) -> FactoryBatch[M]:
        return FactoryBatch(self._factory.sequence(*items), self._count)

    def make(self, **overrides: Any) -> list[M]:
        return self._factory.make_many(self._count, **overrides)

    async def create(self, **overrides: Any) -> list[M]:
        return await self._factory.create_many(self._count, **overrides)


__all__ = ["Factory", "FactoryBatch"]
