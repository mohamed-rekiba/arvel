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
    from collections.abc import Callable

    from arvel.database.model import Model


class Factory[M: Model]:
    """Base model factory. Define ``model`` + ``definition()`` on a subclass."""

    model: type[M]

    def __init__(self) -> None:
        self._states: list[dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]]] = []
        self._sequence: list[dict[str, Any]] = []

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

    def _attributes(self, overrides: dict[str, Any], index: int = 0) -> dict[str, Any]:
        # Resolution order (later wins): definition() → states (in call order) → sequence[index] →
        # explicit overrides. A *callable* state therefore sees definition + earlier states, NOT the
        # sequence value for its index (sequence is applied after states).
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

    def make(self, **overrides: Any) -> M:
        """Build one unsaved model instance."""
        return self.model(**self._attributes(overrides))

    async def create(self, **overrides: Any) -> M:
        """Build and persist one model instance."""
        return await self.model.create(**self._attributes(overrides))

    def make_many(self, count: int, **overrides: Any) -> list[M]:
        """Build ``count`` unsaved instances (sequence applied per index)."""
        return [self.model(**self._attributes(overrides, i)) for i in range(count)]

    async def create_many(self, count: int, **overrides: Any) -> list[M]:
        """Build and persist ``count`` instances (sequence applied per index)."""
        return [await self.model.create(**self._attributes(overrides, i)) for i in range(count)]

    def count(self, count: int) -> FactoryBatch[M]:
        """Begin a fluent batch — ``factory().count(3).create()`` (Laravel ``count``)."""
        return FactoryBatch(self, count)


class FactoryBatch[M: Model]:
    """A fluent ``count``-bound batch whose ``make``/``create`` return lists. ``state``/``sequence``
    keep chaining (they re-wrap the underlying factory)."""

    def __init__(self, factory: Factory[M], count: int) -> None:
        self._factory = factory
        self._count = count

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
