"""Eloquent-style ``Collection[T]`` — a typed ``list[T]`` subclass with chainable helpers.

The single canonical Collection for the whole framework lives here;
downstream layers (``arvel.database``, ``arvel.http``,...) re-export it.

Because ``Collection`` is a ``list`` subclass, ``isinstance(c, list)`` is ``True``
and indexing, slicing, iteration, and ``len`` all work without ceremony.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Generic, TypeVar, cast

T = TypeVar("T")
U = TypeVar("U")


class Collection(list[T], Generic[T]):
    """Typed list subclass with chainable Eloquent-style helpers.

    Single canonical Collection for the whole framework. ``isinstance(c, list)``
    is True; indexing, iteration, slicing, and ``len`` work without ceremony.
    """

    # ── transformation ──────────────────────────────────────────────────────

    def map(self, fn: Callable[[T], U]) -> Collection[U]:
        return Collection(fn(item) for item in self)

    def filter(self, fn: Callable[[T], bool]) -> Collection[T]:
        return Collection(item for item in self if fn(item))

    def reject(self, fn: Callable[[T], bool]) -> Collection[T]:
        return Collection(item for item in self if not fn(item))

    def reduce(self, fn: Callable[[U, T], U], initial: U) -> U:
        acc = initial
        for item in self:
            acc = fn(acc, item)
        return acc

    def pluck(self, key: str) -> Collection[Any]:
        return Collection(getattr(item, key) for item in self)

    def unique(self, key: str | None = None) -> Collection[T]:
        seen: set[Any] = set()
        result: list[T] = []
        for item in self:
            marker: Any = getattr(item, key) if key else item
            if marker in seen:
                continue
            seen.add(marker)
            result.append(item)
        return Collection(result)

    def flatten(self) -> Collection[Any]:
        result: list[Any] = []
        for item in self:
            if isinstance(item, list):
                result.extend(cast("list[Any]", item))
            else:
                result.append(item)
        return Collection(result)

    def sort_by(self, key: str, *, descending: bool = False) -> Collection[T]:
        return Collection(sorted(self, key=lambda x: getattr(x, key), reverse=descending))

    def reverse(self) -> Collection[T]:  # type: ignore[override]
        return Collection(reversed(self))

    def take(self, n: int) -> Collection[T]:
        return Collection(self[:n]) if n >= 0 else Collection(self[n:])

    def skip(self, n: int) -> Collection[T]:
        return Collection(self[n:])

    def chunk(self, size: int) -> Collection[Collection[T]]:
        if size <= 0:
            msg = "chunk size must be > 0"
            raise ValueError(msg)
        return Collection(Collection(self[i : i + size]) for i in range(0, len(self), size))

    def zip(self, *others: list[Any]) -> Collection[tuple[Any, ...]]:
        return Collection(zip(self, *others, strict=False))

    # ── lookup / inspection ──────────────────────────────────────────────────

    def first(self, fn: Callable[[T], bool] | None = None) -> T | None:
        if fn is None:
            return self[0] if self else None
        for item in self:
            if fn(item):
                return item
        return None

    def first_where(self, **kwargs: object) -> T | None:
        for item in self:
            if all(getattr(item, k, None) == v for k, v in kwargs.items()):
                return item
        return None

    def last(self, fn: Callable[[T], bool] | None = None) -> T | None:
        if fn is None:
            return self[-1] if self else None
        for item in reversed(self):
            if fn(item):
                return item
        return None

    def contains(self, fn_or_value: Callable[[T], bool] | T) -> bool:
        if callable(fn_or_value):
            return any(fn_or_value(item) for item in self)
        return fn_or_value in self

    def find(self, value: T, /) -> T | None:
        for item in self:
            if item == value:
                return item
        return None

    def every(self, fn: Callable[[T], bool]) -> bool:
        return all(fn(item) for item in self)

    def some(self, fn: Callable[[T], bool]) -> bool:
        return any(fn(item) for item in self)

    def is_empty(self) -> bool:
        return len(self) == 0

    def is_not_empty(self) -> bool:
        return len(self) > 0

    # ── aggregates ───────────────────────────────────────────────────────────

    def sum(self, key: str) -> Any:
        if not self:
            return None
        return sum(getattr(item, key, 0) or 0 for item in self)

    def avg(self, key: str) -> float | None:
        if not self:
            return None
        return sum(getattr(item, key, 0) or 0 for item in self) / len(self)

    def max(self, key: str) -> Any:
        if not self:
            return None
        return max(getattr(item, key) for item in self)

    def min(self, key: str) -> Any:
        if not self:
            return None
        return min(getattr(item, key) for item in self)

    def count_by(self, fn: Callable[[T], Any]) -> dict[Any, int]:
        result: dict[Any, int] = {}
        for item in self:
            k = fn(item)
            result[k] = result.get(k, 0) + 1
        return result

    # ── grouping ─────────────────────────────────────────────────────────────

    def group_by(self, key: str | Callable[[T], Any]) -> dict[Any, Collection[T]]:
        result: dict[Any, Collection[T]] = {}
        for item in self:
            k = key(item) if callable(key) else getattr(item, key)
            if k not in result:
                result[k] = Collection()
            result[k].append(item)
        return result

    def key_by(self, key: str) -> dict[Any, T]:
        return {getattr(item, key): item for item in self}

    # ── set operations ───────────────────────────────────────────────────────

    def intersect(self, other: list[T]) -> Collection[T]:
        other_ids = {id(x) for x in other}
        return Collection(item for item in self if id(item) in other_ids)

    def diff(self, other: list[T]) -> Collection[T]:
        other_ids = {id(x) for x in other}
        return Collection(item for item in self if id(item) not in other_ids)

    def only(self, *values: T) -> Collection[T]:
        # `in` compares by ==, so this works for unhashable members too.
        return Collection(item for item in self if item in values)

    def except_(self, *values: T) -> Collection[T]:
        return Collection(item for item in self if item not in values)

    def merge(self, other: list[T]) -> Collection[T]:
        return Collection(list(self) + list(other))

    # ── serialisation ────────────────────────────────────────────────────────

    def to_json(self, **json_kwargs: Any) -> str:
        return json.dumps([_serialize(item) for item in self], **json_kwargs)

    def to_array(self) -> list[T]:
        return list(self)

    def values(self) -> Collection[T]:
        return Collection(self)


def _serialize(item: Any) -> Any:
    """Best-effort JSON-friendly conversion: Eloquent-style ``to_dict`` first,
    then Pydantic ``model_dump``, otherwise the value unchanged.
    """
    if hasattr(item, "to_dict"):
        return item.to_dict()
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return item


__all__ = ["Collection"]
