"""Factories — typed test data builders."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Generic, Self, TypeIs, TypeVar

from arvel.database.session import get_active_session

if TYPE_CHECKING:
    from arvel.database.model import Model

T = TypeVar("T", bound="Model")

# Callback signatures used by ``after_making`` / ``after_creating``. The
# second positional argument is the "faker" — currently always ``None``,
# but kept in the contract for future Faker integration.
AfterMakingCallback = Callable[[T, Any], None]
AfterCreatingCallback = Callable[[T, Any], "None | Awaitable[Any]"]

# Global sequence counters keyed by (factory_class, field_name)
_SEQUENCE_COUNTERS: dict[str, int] = {}


def sequence(factory_cls_name: str, field: str) -> int:
    """Return the next integer in a named sequence starting at 1."""
    key = f"{factory_cls_name}.{field}"
    _SEQUENCE_COUNTERS[key] = _SEQUENCE_COUNTERS.get(key, 0) + 1
    return _SEQUENCE_COUNTERS[key]


def _is_str_any_dict(value: object) -> TypeIs[dict[str, Any]]:
    """TypeIs narrowing ``dict | Callable`` overload params to ``dict[str, Any]``.

    A direct ``isinstance(x, dict)`` collapses the parameter to
    ``dict[Unknown, Unknown]`` under pyright; ``TypeIs`` (PEP 742) returns
    the precise generic shape and narrows BOTH branches — unlike
    ``TypeGuard`` which only narrows the positive branch.
    """
    return isinstance(value, dict)


class Factory(Generic[T]):
    """Base class for typed factories.

    Subclass and override ``model`` (class attr) and ``definition()`` (returns
    the attribute dict for a new instance).

    Use ``count(n)`` to multiply, ``state(overrides)`` to amend defaults,
    ``has(...)`` / ``for_(...)`` to attach relationships.
    """

    model: type[T]

    def __init__(self) -> None:
        self._count: int = 1
        self._state_overrides: list[dict[str, Any]] = []
        self._has: list[tuple[str, Factory[Any], int]] = []
        self._for: list[tuple[str, Any]] = []
        self._sequences: list[tuple[str, Callable[[int], Any]]] = []
        self._after_making: list[AfterMakingCallback[T]] = []
        self._after_creating: list[AfterCreatingCallback[T]] = []
        self._recycle: dict[type[Any], list[Any]] = {}

    def definition(self) -> dict[str, Any]:
        raise NotImplementedError(
            f"{type(self).__name__}.definition() must return a dict of attributes."
        )

    def seq(self, field: str) -> int:
        """Return the next integer in a sequence scoped to this factory + field."""
        return sequence(type(self).__name__, field)

    def count(self, n: int) -> Self:
        if n < 0:
            raise ValueError("count must be >= 0")
        self._count = n
        return self

    def state(self, overrides: dict[str, Any] | Callable[[], dict[str, Any]]) -> Self:
        payload = overrides if _is_str_any_dict(overrides) else overrides()
        self._state_overrides.append(payload)
        return self

    def has(self, relation: str, factory: Factory[Any], *, count: int = 1) -> Self:
        self._has.append((relation, factory, count))
        return self

    def for_(self, relation: str, instance: Any) -> Self:
        self._for.append((relation, instance))
        return self

    def sequence(self, field: str, fn: Callable[[int], Any]) -> Self:
        """Override ``field`` on each call with ``fn(n)`` (``n`` increments per instance)."""
        self._sequences.append((field, fn))
        return self

    def after_making(self, callback: AfterMakingCallback[T]) -> Self:
        """Register a callback called with ``(instance, faker)`` after each make()."""
        self._after_making.append(callback)
        return self

    def after_creating(self, callback: AfterCreatingCallback[T]) -> Self:
        """Register a callback called with ``(instance, faker)`` after each create()."""
        self._after_creating.append(callback)
        return self

    def recycle(self, instances: list[Any]) -> Self:
        """Reuse existing instances instead of creating new ones for a given model type."""
        if instances:
            self._recycle[type(instances[0])] = list(instances)
        return self

    def make(self) -> T | list[T]:
        instances: list[T] = []
        seq_counters: dict[str, int] = {}
        for _ in range(self._count):
            attrs = self.definition()
            for override in self._state_overrides:
                attrs.update(override)
            for field, fn in self._sequences:
                seq_counters[field] = seq_counters.get(field, 0) + 1
                attrs[field] = fn(seq_counters[field])
            for rel, parent in self._for:
                fk_attr, fk_val = _resolve_for_attr(self.model, rel, parent)
                attrs[fk_attr] = fk_val
            instance = self.model(**attrs)
            for cb in self._after_making:
                cb(instance, None)
            instances.append(instance)
        return instances[0] if self._count == 1 else instances

    async def create(self) -> T | list[T]:
        import asyncio

        session = get_active_session()
        made = self.make()
        instances = made if isinstance(made, list) else [made]
        for inst in instances:
            session.add(inst)
        await session.flush()
        for inst in instances:
            for rel, child_factory, n in self._has:
                child_factory.count(n).for_(_back_ref_of(inst, rel), inst)
                await child_factory.create()
                # Expire the relationship collection so subsequent accesses
                # (and eager-load queries) see the new children from the DB.
                session.expire(inst, [rel])
            for cb in self._after_creating:
                result = cb(inst, None)
                if asyncio.iscoroutine(result):
                    await result
        return instances[0] if self._count == 1 else instances


def _resolve_for_attr(model: type[Any], rel: str, parent: Any) -> tuple[str, Any]:
    """Resolve a for_() relationship name to an (attr_name, value) pair.

    With MappedAsDataclass, many-to-one relationships are init=False.  When
    ``rel`` is not a constructor parameter we look up the FK column for that
    relationship and return ``(fk_column_key, parent.pk_value)`` instead, so
    the caller can pass the FK directly.
    """
    import dataclasses

    from sqlalchemy.orm import Mapper, class_mapper

    # Check if rel is directly accepted by __init__
    try:
        init_fields: set[str] = {f.name for f in dataclasses.fields(model) if f.init}
    except TypeError:
        init_fields = set()

    if rel in init_fields:
        return rel, parent

    # rel is init=False — resolve to the FK column key
    try:
        mapper = class_mapper(model)
        rel_prop = mapper.relationships.get(rel)
        if rel_prop is not None:
            local_cols = list(rel_prop.local_columns)
            if local_cols:
                fk_key = mapper.get_property_by_column(local_cols[0]).key
                # Get the PK value from the parent instance
                parent_mapper: Mapper[Any] = class_mapper(parent.__class__)
                pk_col = parent_mapper.primary_key[0]
                pk_key = parent_mapper.get_property_by_column(pk_col).key
                return str(fk_key), getattr(parent, pk_key)
    except Exception:  # noqa: BLE001 — best-effort introspection; fall back to direct assignment
        return rel, parent

    return rel, parent


def _back_ref_of(parent: Any, relation: str) -> str:
    """Best-effort: child factory's `for_` key is usually the relation's back_populates."""
    from sqlalchemy.orm import Mapper, class_mapper

    # ``parent.__class__`` flows back as ``Any`` (parent is ``Any``), which
    # both checkers accept as compatible with ``type[Any]`` — unlike
    # ``type(parent)``, which pyright narrows to ``type[Unknown]`` and mypy
    # narrows to ``type[Any]`` (the two then disagree about redundant casts).
    mapper: Mapper[Any] = class_mapper(parent.__class__)
    rel = mapper.relationships.get(relation)
    if rel is not None and rel.back_populates:
        return str(rel.back_populates)
    return relation


__all__ = ["Factory", "sequence"]
