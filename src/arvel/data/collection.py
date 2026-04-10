"""Fluent collection wrapping query results.

``ArvelCollection[T]`` extends ``list[T]`` with chainable transformation
methods so callers can work with results fluently instead of dropping to
raw list comprehensions.
"""

from __future__ import annotations

import builtins
import contextlib
import json
import random as _random
import statistics as _statistics
from collections import Counter
from collections.abc import Hashable
from functools import reduce as _reduce
from itertools import islice
from typing import TYPE_CHECKING, Any, TypeVar, overload

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

T = TypeVar("T")
R = TypeVar("R")


class ArvelCollection(list[T]):
    """List subclass with chainable data-manipulation helpers.

    Behaves exactly like a built-in ``list`` for iteration, indexing,
    ``len()``, truthiness, and serialization — but adds fluent methods
    inspired by Laravel's ``Collection``.
    """

    # ------------------------------------------------------------------
    # Element access
    # ------------------------------------------------------------------

    def first(self, default: T | None = None) -> T | None:
        """Return the first item, or *default* if the collection is empty."""
        return self[0] if self else default

    def last(self, default: T | None = None) -> T | None:
        """Return the last item, or *default* if the collection is empty."""
        return self[-1] if self else default

    # ------------------------------------------------------------------
    # Transformation
    # ------------------------------------------------------------------

    def map(self, fn: Callable[[T], R]) -> ArvelCollection[R]:
        """Apply *fn* to each item and return a new collection."""
        return ArvelCollection(fn(item) for item in self)

    def flat_map(self, fn: Callable[[T], list[R]]) -> ArvelCollection[R]:
        """Map then flatten one level."""
        result: list[R] = []
        for item in self:
            result.extend(fn(item))
        return ArvelCollection(result)

    def filter(self, fn: Callable[[T], bool] | None = None) -> ArvelCollection[T]:
        """Keep items where *fn* returns truthy, or all truthy items if *fn* is None."""
        if fn is None:
            return ArvelCollection(item for item in self if item)
        return ArvelCollection(item for item in self if fn(item))

    def reject(self, fn: Callable[[T], bool]) -> ArvelCollection[T]:
        """Remove items where *fn* returns truthy."""
        return ArvelCollection(item for item in self if not fn(item))

    def each(self, fn: Callable[[T], object]) -> ArvelCollection[T]:
        """Call *fn* on each item for side effects; return self."""
        for item in self:
            fn(item)
        return self

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def pluck(self, key: str) -> ArvelCollection[Any]:
        """Extract a single attribute or dict key from each item."""
        return ArvelCollection(_extract(item, key) for item in self)

    def values(self) -> ArvelCollection[T]:
        """Return a re-indexed copy (removes gaps after filtering)."""
        return ArvelCollection(self)

    # ------------------------------------------------------------------
    # Filtering / searching
    # ------------------------------------------------------------------

    def where(self, key: str, value: Any) -> ArvelCollection[T]:
        """Keep items where ``item.key == value`` (or ``item[key] == value``)."""
        return ArvelCollection(item for item in self if _extract(item, key, _SENTINEL) == value)

    def where_in(self, key: str, values: list[Any] | set[Any]) -> ArvelCollection[T]:
        """Keep items where ``item.key`` is in *values*."""
        value_set = set(values)
        return ArvelCollection(item for item in self if _extract(item, key, _SENTINEL) in value_set)

    def first_where(self, key: str, value: Any) -> T | None:
        """Return the first item matching ``key == value``, or None."""
        for item in self:
            if _extract(item, key, _SENTINEL) == value:
                return item
        return None

    def contains(self, fn_or_value: Callable[[T], bool] | Any) -> bool:
        """Check if *any* item satisfies *fn* or equals *value*."""
        if callable(fn_or_value):
            return any(fn_or_value(item) for item in self)
        return fn_or_value in self

    # ------------------------------------------------------------------
    # Grouping / chunking
    # ------------------------------------------------------------------

    def group_by(self, key: str | Callable[[T], Hashable]) -> dict[Any, ArvelCollection[T]]:
        """Group items by a key attribute name or callable."""
        result: dict[Any, ArvelCollection[T]] = {}
        if isinstance(key, str):
            for item in self:
                result.setdefault(_extract(item, key), ArvelCollection()).append(item)
        else:
            for item in self:
                result.setdefault(key(item), ArvelCollection()).append(item)
        return result

    def chunk(self, size: int) -> ArvelCollection[ArvelCollection[T]]:
        """Split into sub-collections of at most *size* items."""
        if size < 1:
            msg = "chunk size must be >= 1"
            raise ValueError(msg)
        it: Iterator[T] = iter(self)
        chunks: list[ArvelCollection[T]] = []
        while True:
            batch = ArvelCollection(islice(it, size))
            if not batch:
                break
            chunks.append(batch)
        return ArvelCollection(chunks)

    # ------------------------------------------------------------------
    # Ordering / uniqueness
    # ------------------------------------------------------------------

    def sort_by(
        self,
        key: str | Callable[[T], Any],
        *,
        descending: bool = False,
    ) -> ArvelCollection[T]:
        """Return a new collection sorted by *key*."""
        if isinstance(key, str):
            attr_name = key

            def sort_fn(item: T) -> Any:
                return _extract(item, attr_name)
        else:
            sort_fn = key
        return ArvelCollection(
            sorted(self, key=sort_fn, reverse=descending),
        )

    def unique(self, key: str | Callable[[T], Hashable] | None = None) -> ArvelCollection[T]:
        """Remove duplicates, preserving order.

        If *key* is given, uniqueness is determined by the key value.
        """
        seen: set[Any] = set()
        result: list[T] = []
        if key is None:
            for item in self:
                identity: Any = id(item) if not isinstance(item, Hashable) else item
                if identity not in seen:
                    seen.add(identity)
                    result.append(item)
        elif isinstance(key, str):
            for item in self:
                identity = _extract(item, key)
                if identity not in seen:
                    seen.add(identity)
                    result.append(item)
        else:
            for item in self:
                identity = key(item)
                if identity not in seen:
                    seen.add(identity)
                    result.append(item)
        return ArvelCollection(result)

    def reverse(self) -> ArvelCollection[T]:  # type: ignore[override]  # ty: ignore[invalid-method-override]  # Intentional: non-mutating API
        """Return a new reversed collection (non-mutating).

        Intentionally overrides ``list.reverse()`` to return a new
        collection instead of mutating in place, matching the immutable
        API style of all other ArvelCollection methods.
        """
        return ArvelCollection(reversed(self))

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def count(self) -> int:  # type: ignore[override]  # ty: ignore[invalid-method-override]  # Intentional: Laravel-style count()
        """Return the number of items (alias for ``len()``).

        Intentionally overrides ``list.count(value)`` to return the
        collection length without requiring a value argument, matching
        Laravel's Collection.count() API.
        """
        return len(self)

    def sum(self, key: str | Callable[[T], Any] | None = None) -> Any:
        """Sum item values, optionally by attribute or callable."""
        if key is None:
            return builtins.sum(self)
        if isinstance(key, str):
            return builtins.sum(_extract(item, key, 0) for item in self)
        return builtins.sum(key(item) for item in self)

    def avg(self, key: str | Callable[[T], Any] | None = None) -> float:
        """Return the average value."""
        if not self:
            return 0.0
        total = self.sum(key)
        return total / len(self)

    def min(self, key: str | Callable[[T], Any] | None = None) -> Any:
        """Return the minimum value."""
        if not self:
            return None
        if key is None:
            return builtins.min(self)
        if isinstance(key, str):
            return builtins.min(_extract(item, key, None) for item in self)
        return builtins.min(key(item) for item in self)

    def max(self, key: str | Callable[[T], Any] | None = None) -> Any:
        """Return the maximum value."""
        if not self:
            return None
        if key is None:
            return builtins.max(self)
        if isinstance(key, str):
            return builtins.max(_extract(item, key, None) for item in self)
        return builtins.max(key(item) for item in self)

    # ------------------------------------------------------------------
    # Slicing
    # ------------------------------------------------------------------

    def take(self, n: int) -> ArvelCollection[T]:
        """Take the first *n* items (negative *n* takes from the end)."""
        if n < 0:
            return ArvelCollection(self[n:])
        return ArvelCollection(self[:n])

    def skip(self, n: int) -> ArvelCollection[T]:
        """Skip the first *n* items."""
        return ArvelCollection(self[n:])

    def slice(self, offset: int, length: int | None = None) -> ArvelCollection[T]:
        """Extract a portion starting at *offset*."""
        if length is None:
            return ArvelCollection(self[offset:])
        return ArvelCollection(self[offset : offset + length])

    def nth(self, step: int, offset: int = 0) -> ArvelCollection[T]:
        """Return every *step*-th item, starting at *offset*."""
        return ArvelCollection(self[offset::step])

    def for_page(self, page: int, per_page: int) -> ArvelCollection[T]:
        """Return a page of results (1-indexed)."""
        start = (page - 1) * per_page
        return ArvelCollection(self[start : start + per_page])

    def take_while(self, fn: Callable[[T], bool]) -> ArvelCollection[T]:
        """Take items while *fn* returns truthy."""
        result: list[T] = []
        for item in self:
            if not fn(item):
                break
            result.append(item)
        return ArvelCollection(result)

    def take_until(self, fn: Callable[[T], bool]) -> ArvelCollection[T]:
        """Take items until *fn* returns truthy."""
        result: list[T] = []
        for item in self:
            if fn(item):
                break
            result.append(item)
        return ArvelCollection(result)

    def skip_while(self, fn: Callable[[T], bool]) -> ArvelCollection[T]:
        """Skip items while *fn* returns truthy."""
        skipping = True
        result: list[T] = []
        for item in self:
            if skipping and fn(item):
                continue
            skipping = False
            result.append(item)
        return ArvelCollection(result)

    def skip_until(self, fn: Callable[[T], bool]) -> ArvelCollection[T]:
        """Skip items until *fn* returns truthy."""
        skipping = True
        result: list[T] = []
        for item in self:
            if skipping:
                if fn(item):
                    skipping = False
                    result.append(item)
                continue
            result.append(item)
        return ArvelCollection(result)

    # ------------------------------------------------------------------
    # Set operations
    # ------------------------------------------------------------------

    def merge(self, other: Iterable[T]) -> ArvelCollection[T]:
        """Combine with another iterable."""
        return ArvelCollection([*self, *other])

    def concat(self, other: Iterable[T]) -> ArvelCollection[T]:
        """Alias for ``merge``."""
        return self.merge(other)

    def diff(self, other: Iterable[Any]) -> ArvelCollection[T]:
        """Items in this collection but not in *other*."""
        other_set = set(other)
        return ArvelCollection(item for item in self if item not in other_set)

    def intersect(self, other: Iterable[Any]) -> ArvelCollection[T]:
        """Items present in both this collection and *other*."""
        other_set = set(other)
        return ArvelCollection(item for item in self if item in other_set)

    def zip(self, other: Iterable[R]) -> ArvelCollection[tuple[T, R]]:
        """Pair items with another iterable."""
        return ArvelCollection(builtins.zip(self, other, strict=False))

    # ------------------------------------------------------------------
    # Partitioning / splitting
    # ------------------------------------------------------------------

    def partition(self, fn: Callable[[T], bool]) -> tuple[ArvelCollection[T], ArvelCollection[T]]:
        """Split into two collections: items passing *fn* and items failing."""
        passing: list[T] = []
        failing: list[T] = []
        for item in self:
            (passing if fn(item) else failing).append(item)
        return ArvelCollection(passing), ArvelCollection(failing)

    def split(self, n: int) -> ArvelCollection[ArvelCollection[T]]:
        """Split into *n* groups as evenly as possible."""
        if n < 1:
            msg = "split count must be >= 1"
            raise ValueError(msg)
        k, m = divmod(len(self), n)
        groups: list[ArvelCollection[T]] = []
        start = 0
        for i in range(n):
            end = start + k + (1 if i < m else 0)
            groups.append(ArvelCollection(self[start:end]))
            start = end
        return ArvelCollection(groups)

    def sliding(self, size: int, step: int = 1) -> ArvelCollection[ArvelCollection[T]]:
        """Return a sliding window of *size* items, advancing by *step*."""
        if size < 1:
            msg = "window size must be >= 1"
            raise ValueError(msg)
        windows: list[ArvelCollection[T]] = []
        for i in range(0, len(self) - size + 1, step):
            windows.append(ArvelCollection(self[i : i + size]))
        return ArvelCollection(windows)

    # ------------------------------------------------------------------
    # Flattening
    # ------------------------------------------------------------------

    def flatten(self, depth: int = -1) -> ArvelCollection[Any]:
        """Flatten nested iterables (excluding strings/dicts).

        *depth=-1* flattens fully; *depth=1* flattens one level.
        """
        return ArvelCollection(_flatten_iter(self, depth))

    def collapse(self) -> ArvelCollection[Any]:
        """Flatten one level of nesting."""
        return self.flatten(depth=1)

    # ------------------------------------------------------------------
    # Conditional flow
    # ------------------------------------------------------------------

    def pipe(self, fn: Callable[[ArvelCollection[T]], R]) -> R:
        """Pass the entire collection through *fn* and return the result."""
        return fn(self)

    def tap(self, fn: Callable[[ArvelCollection[T]], object]) -> ArvelCollection[T]:
        """Call *fn* with the collection for side effects, return self."""
        fn(self)
        return self

    def when(
        self,
        condition: bool,
        fn: Callable[[ArvelCollection[T]], ArvelCollection[T]],
        default: Callable[[ArvelCollection[T]], ArvelCollection[T]] | None = None,
    ) -> ArvelCollection[T]:
        """Apply *fn* if *condition* is truthy, otherwise apply *default*."""
        if condition:
            return fn(self)
        if default is not None:
            return default(self)
        return self

    def unless(
        self,
        condition: bool,
        fn: Callable[[ArvelCollection[T]], ArvelCollection[T]],
        default: Callable[[ArvelCollection[T]], ArvelCollection[T]] | None = None,
    ) -> ArvelCollection[T]:
        """Apply *fn* if *condition* is falsy, otherwise apply *default*."""
        if not condition:
            return fn(self)
        if default is not None:
            return default(self)
        return self

    # ------------------------------------------------------------------
    # Reduction / folding
    # ------------------------------------------------------------------

    def reduce(self, fn: Callable[[R, T], R], initial: R) -> R:
        """Fold left over the collection."""
        return _reduce(fn, self, initial)

    def every(self, fn: Callable[[T], bool]) -> bool:
        """Return ``True`` if all items satisfy *fn*."""
        return all(fn(item) for item in self)

    def some(self, fn: Callable[[T], bool]) -> bool:
        """Return ``True`` if any item satisfies *fn*. Alias for callable contains."""
        return any(fn(item) for item in self)

    # ------------------------------------------------------------------
    # Searching
    # ------------------------------------------------------------------

    @overload
    def search(self, value: Callable[[T], bool]) -> int | None: ...
    @overload
    def search(self, value: T) -> int | None: ...
    def search(self, value: T | Callable[[T], bool]) -> int | None:
        """Return the index of the first matching item, or ``None``.

        Accepts a value or a callable predicate.
        """
        if callable(value):
            predicate: Callable[[T], bool] = value  # type: ignore[assignment]  # ty: ignore[invalid-assignment]  # overloads guarantee Callable[[T], bool]
            for i, item in enumerate(self):
                if predicate(item):
                    return i
            return None
        try:
            return self.index(value)
        except ValueError:
            return None

    def sole(self, fn: Callable[[T], bool] | None = None) -> T:
        """Return the only item matching *fn*, or the only item if *fn* is None.

        Raises ``ValueError`` if zero or more than one match.
        """
        if fn is None:
            if len(self) != 1:
                msg = f"Expected exactly 1 item, got {len(self)}"
                raise ValueError(msg)
            return self[0]
        matches = [item for item in self if fn(item)]
        if len(matches) != 1:
            msg = f"Expected exactly 1 matching item, got {len(matches)}"
            raise ValueError(msg)
        return matches[0]

    # ------------------------------------------------------------------
    # String
    # ------------------------------------------------------------------

    def implode(self, glue: str, key: str | None = None) -> str:
        """Join items into a string, optionally plucking *key* first."""
        if key is not None:
            return glue.join(str(_extract(item, key, "")) for item in self)
        return glue.join(str(item) for item in self)

    # ------------------------------------------------------------------
    # Randomness
    # ------------------------------------------------------------------

    def random(self, count: int = 1) -> T | ArvelCollection[T]:
        """Return *count* random items. Returns a single item when count=1."""
        if not self:
            msg = "Cannot get random items from an empty collection"
            raise ValueError(msg)
        if count == 1:
            return _random.choice(self)  # noqa: S311 — not cryptographic
        return ArvelCollection(
            _random.sample(self, min(count, len(self))),
        )

    def shuffle(self) -> ArvelCollection[T]:
        """Return a new collection with items in random order."""
        items = list(self)
        _random.shuffle(items)
        return ArvelCollection(items)

    # ------------------------------------------------------------------
    # Extended aggregation
    # ------------------------------------------------------------------

    def median(self, key: str | Callable[[T], Any] | None = None) -> float:
        """Return the statistical median."""
        values = self._numeric_values(key)
        if not values:
            return 0.0
        return _statistics.median(values)

    def mode(self, key: str | Callable[[T], Any] | None = None) -> ArvelCollection[Any]:
        """Return the most common value(s)."""
        values = self._numeric_values(key)
        if not values:
            return ArvelCollection()
        counter = Counter(values)
        max_count = max(counter.values())
        return ArvelCollection(v for v, c in counter.items() if c == max_count)

    def count_by(self, fn: Callable[[T], Any] | str | None = None) -> dict[Any, int]:
        """Count occurrences grouped by the return value of *fn* or attribute *key*."""
        counter: dict[Any, int] = {}
        if fn is None:
            for item in self:
                counter[item] = counter.get(item, 0) + 1
        elif isinstance(fn, str):
            for item in self:
                k = _extract(item, fn)
                counter[k] = counter.get(k, 0) + 1
        else:
            for item in self:
                k = fn(item)
                counter[k] = counter.get(k, 0) + 1
        return counter

    def duplicates(self, key: str | Callable[[T], Any] | None = None) -> ArvelCollection[T]:
        """Return items that appear more than once."""
        identity_fn = _make_identity_fn(key)
        seen: dict[Any, int] = {}
        for item in self:
            identity = identity_fn(item)
            seen[identity] = seen.get(identity, 0) + 1
        dup_keys = {k for k, v in seen.items() if v > 1}
        result: list[T] = []
        added: set[Any] = set()
        for item in self:
            identity = identity_fn(item)
            if identity in dup_keys and identity not in added:
                result.append(item)
                added.add(identity)
        return ArvelCollection(result)

    # ------------------------------------------------------------------
    # Mutation (returns new collections for immutability by default)
    # ------------------------------------------------------------------

    def prepend(self, item: T) -> ArvelCollection[T]:
        """Return a new collection with *item* at the front."""
        return ArvelCollection([item, *self])

    def push(self, *items: T) -> ArvelCollection[T]:
        """Return a new collection with *items* appended."""
        return ArvelCollection([*self, *items])

    def pop_item(self) -> tuple[T, ArvelCollection[T]]:
        """Return the last item and a new collection without it.

        Named ``pop_item`` to avoid shadowing ``list.pop``.
        """
        if not self:
            msg = "Cannot pop from an empty collection"
            raise ValueError(msg)
        return self[-1], ArvelCollection(self[:-1])

    def shift(self) -> tuple[T, ArvelCollection[T]]:
        """Return the first item and a new collection without it."""
        if not self:
            msg = "Cannot shift from an empty collection"
            raise ValueError(msg)
        return self[0], ArvelCollection(self[1:])

    # ------------------------------------------------------------------
    # Niche utilities
    # ------------------------------------------------------------------

    def ensure(self, *types: type) -> ArvelCollection[T]:
        """Verify every item is an instance of one of *types*.

        Returns self if all items match, raises ``TypeError`` otherwise.
        """
        for item in self:
            if not isinstance(item, types):
                expected = " | ".join(t.__name__ for t in types)
                msg = f"Expected {expected}, got {type(item).__name__}"
                raise TypeError(msg)
        return self

    def percentage(self, fn: Callable[[T], bool], precision: int = 2) -> float:
        """Return the percentage of items satisfying *fn*."""
        if not self:
            return 0.0
        count = builtins.sum(1 for item in self if fn(item))
        return round(count / len(self) * 100, precision)

    def multiply(self, n: int) -> ArvelCollection[T]:
        """Repeat the collection *n* times."""
        return ArvelCollection(list(self) * n)

    def after(self, fn_or_value: Callable[[T], bool] | Any) -> T | None:
        """Return the item after the first match, or ``None``."""
        it = iter(self)
        if callable(fn_or_value):
            for item in it:
                if fn_or_value(item):
                    return next(it, None)
        else:
            for item in it:
                if item == fn_or_value:
                    return next(it, None)
        return None

    def before(self, fn_or_value: Callable[[T], bool] | Any) -> T | None:
        """Return the item before the first match, or ``None``."""
        prev: T | None = None
        if callable(fn_or_value):
            for item in self:
                if fn_or_value(item):
                    return prev
                prev = item
        else:
            for item in self:
                if item == fn_or_value:
                    return prev
                prev = item
        return None

    def select(self, *keys: str) -> ArvelCollection[dict[str, Any]]:
        """Pick only the given *keys* from each item (dict or object)."""

        def _pick(item: Any) -> dict[str, Any]:
            if isinstance(item, dict):
                return {k: item.get(k) for k in keys}
            return {k: getattr(item, k, None) for k in keys}

        return ArvelCollection(_pick(item) for item in self)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _numeric_values(self, key: str | Callable[[T], Any] | None = None) -> list[float]:
        """Extract numeric values for statistical methods."""
        values: list[float] = []
        if key is None:

            def extractor(item: T) -> Any:
                return item
        elif isinstance(key, str):
            attr = key

            def extractor(item: T) -> Any:
                return _extract(item, attr)
        else:
            extractor = key
        for item in self:
            v: Any = extractor(item)
            if v is not None:
                with contextlib.suppress(TypeError, ValueError):
                    values.append(float(v))
        return values

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def to_list(self) -> list[T]:
        """Return a plain Python list."""
        return list(self)

    def to_dict(self, key: str) -> dict[Any, T]:
        """Key items by an attribute, returning a dict."""
        result: dict[Any, T] = {}
        for item in self:
            result[_extract(item, key)] = item
        return result

    def is_empty(self) -> bool:
        return len(self) == 0

    def is_not_empty(self) -> bool:
        return len(self) > 0

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def _serialize_item(self, item: Any) -> Any:
        """Convert a single item to a JSON-safe representation."""
        dump = getattr(item, "model_dump", None)
        if callable(dump):
            return dump()
        return item

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize the collection to a JSON string.

        Calls ``model_dump()`` on Pydantic/ArvelModel items so the
        output is always plain dicts that ``json.dumps`` can handle.
        """
        serialized = [self._serialize_item(item) for item in self]
        return json.dumps(serialized, indent=indent, default=str)

    def __str__(self) -> str:
        return self.to_json()

    def __repr__(self) -> str:
        return f"ArvelCollection({list.__repr__(self)})"


_SENTINEL = object()


def _extract(item: Any, key: str, default: Any = None) -> Any:
    """Extract a value by key from a dict or by attribute from an object."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _make_identity_fn(key: str | Callable[..., Any] | None) -> Callable[..., Any]:
    """Build an identity extractor from a key, callable, or None."""
    if key is None:
        return lambda item: item
    if callable(key):
        return key
    attr = key
    return lambda item: _extract(item, attr)


def _flatten_iter(items: Any, depth: int) -> list[Any]:
    """Recursively flatten iterables (excluding strings and dicts)."""
    result: list[Any] = []
    for item in items:
        is_flattenable = isinstance(item, (list, tuple, ArvelCollection))
        is_excluded = isinstance(item, (str, bytes, dict))
        if depth != 0 and is_flattenable and not is_excluded:
            next_depth = depth - 1 if depth > 0 else depth
            result.extend(_flatten_iter(item, next_depth))
        else:
            result.append(item)
    return result


def collect[U](items: Iterable[U] | None = None) -> ArvelCollection[U]:
    """Create an ``ArvelCollection`` from any iterable.

    ::

        from arvel.data.collection import collect

        numbers = collect([1, 2, 3, 4, 5])
        names = collect(user.name for user in users)
    """
    if items is None:
        return ArvelCollection()
    return ArvelCollection(items)
