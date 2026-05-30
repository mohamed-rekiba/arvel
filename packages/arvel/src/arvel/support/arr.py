"""``Arr`` — Laravel-parity array/dict facade.

Pure helpers for working with ``list``/``dict``/``Sequence`` values. Sibling
to :class:`arvel.support.Collection` — the Collection is for fluent chaining
on a single list; ``Arr`` is for grab-bag operations across mixed shapes.

Nested-traversal helpers (``dot``, ``undot``, ``get``, ``set``, ``has``) use
``object`` at value positions. After ``isinstance`` narrowing pyright loses
the element type on bare ``list``/``tuple``/``Mapping``; we ``cast`` back to
the invariant ``[str, object]`` form so the strict checker stays happy.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, TypeVar, cast, overload

T = TypeVar("T")
U = TypeVar("U")
V = TypeVar("V")


class Arr:
    """Laravel ``Illuminate\\Support\\Arr`` parity helpers."""

    # ── first / last ───────────────────────────────────────────────────

    @overload
    @staticmethod
    def first(items: Iterable[T]) -> T | None: ...

    @overload
    @staticmethod
    def first(items: Iterable[T], predicate: Callable[[T], bool]) -> T | None: ...

    @overload
    @staticmethod
    def first(
        items: Iterable[T],
        predicate: Callable[[T], bool] | None,
        *,
        default: U,
    ) -> T | U: ...

    @overload
    @staticmethod
    def first(items: Iterable[T], *, default: U) -> T | U: ...

    @staticmethod
    def first(
        items: Iterable[T],
        predicate: Callable[[T], bool] | None = None,
        *,
        default: object = None,
    ) -> Any:
        if predicate is None:
            for item in items:
                return item
            return default
        for item in items:
            if predicate(item):
                return item
        return default

    @overload
    @staticmethod
    def last(items: Iterable[T]) -> T | None: ...

    @overload
    @staticmethod
    def last(items: Iterable[T], predicate: Callable[[T], bool]) -> T | None: ...

    @overload
    @staticmethod
    def last(
        items: Iterable[T],
        predicate: Callable[[T], bool] | None,
        *,
        default: U,
    ) -> T | U: ...

    @overload
    @staticmethod
    def last(items: Iterable[T], *, default: U) -> T | U: ...

    @staticmethod
    def last(
        items: Iterable[T],
        predicate: Callable[[T], bool] | None = None,
        *,
        default: object = None,
    ) -> Any:
        materialized = list(items)
        if predicate is None:
            return materialized[-1] if materialized else default
        for item in reversed(materialized):
            if predicate(item):
                return item
        return default

    # ── flatten ────────────────────────────────────────────────────────

    @staticmethod
    def flatten(items: Iterable[object], *, depth: int = -1) -> list[object]:
        """Flatten nested lists/tuples. ``depth=-1`` (default) flattens fully."""
        result: list[object] = []
        for item in items:
            if Arr._should_recurse(item, depth):
                nested = cast("Iterable[object]", item)
                result.extend(Arr.flatten(nested, depth=depth - 1))
            else:
                result.append(item)
        return result

    @staticmethod
    def _should_recurse(item: object, depth: int) -> bool:
        if depth == 0:
            return False
        return isinstance(item, list | tuple) and not isinstance(item, str | bytes)

    # ── only / except ──────────────────────────────────────────────────

    @staticmethod
    def only(data: Mapping[str, T], keys: Iterable[str]) -> dict[str, T]:
        wanted = set(keys)
        return {k: v for k, v in data.items() if k in wanted}

    @staticmethod
    def except_(data: Mapping[str, T], keys: Iterable[str]) -> dict[str, T]:
        drop = set(keys)
        return {k: v for k, v in data.items() if k not in drop}

    # ── dot / undot ────────────────────────────────────────────────────

    @staticmethod
    def dot(data: Mapping[str, object], prefix: str = "") -> dict[str, object]:
        """Flatten a nested mapping into ``a.b.c`` keys."""
        out: dict[str, object] = {}
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, Mapping) and value:
                nested = cast("Mapping[str, object]", value)
                out.update(Arr.dot(nested, path))
            else:
                out[path] = value
        return out

    @staticmethod
    def undot(data: Mapping[str, object]) -> dict[str, object]:
        """Inverse of :meth:`dot` — rebuild nested dicts from dotted keys."""
        out: dict[str, object] = {}
        for key, value in data.items():
            Arr.set(out, key, value)
        return out

    # ── get / set / has (dot notation) ─────────────────────────────────

    @staticmethod
    def get(data: Mapping[str, object], key: str, default: object = None) -> Any:
        # Walk dotted parts, treating every intermediate mapping as Mapping[str, object].
        # When traversal hits a non-Mapping before consuming all parts, return default.
        parts = key.split(".")
        current: Mapping[str, object] = data
        for i, part in enumerate(parts):
            if part not in current:
                return default
            value: object = current[part]
            if i == len(parts) - 1:
                return value
            if not isinstance(value, Mapping):
                return default
            current = cast("Mapping[str, object]", value)
        return default  # unreachable for non-empty key, makes type checker happy

    @staticmethod
    def set(data: dict[str, object], key: str, value: object) -> None:
        parts = key.split(".")
        cursor: dict[str, object] = data
        for part in parts[:-1]:
            existing = cursor.get(part)
            if not isinstance(existing, dict):
                fresh: dict[str, object] = {}
                cursor[part] = fresh
                cursor = fresh
            else:
                cursor = cast("dict[str, object]", existing)
        cursor[parts[-1]] = value

    @staticmethod
    def has(data: Mapping[str, object], key: str) -> bool:
        parts = key.split(".")
        current: Mapping[str, object] = data
        for i, part in enumerate(parts):
            if part not in current:
                return False
            value: object = current[part]
            if i == len(parts) - 1:
                return True
            if not isinstance(value, Mapping):
                return False
            current = cast("Mapping[str, object]", value)
        return False

    # ── pluck / wrap / prepend / where ────────────────────────────────

    @overload
    @staticmethod
    def pluck(items: Iterable[object], attribute: str) -> list[Any]: ...

    @overload
    @staticmethod
    def pluck(items: Iterable[object], attribute: str, *, key: str) -> dict[Any, Any]: ...

    @staticmethod
    def pluck(
        items: Iterable[object],
        attribute: str,
        *,
        key: str | None = None,
    ) -> Any:
        def _read(item: object, name: str) -> Any:
            if isinstance(item, Mapping):
                mapping = cast("Mapping[str, object]", item)
                return mapping.get(name)
            return getattr(item, name, None)

        if key is None:
            return [_read(item, attribute) for item in items]
        return {_read(item, key): _read(item, attribute) for item in items}

    @staticmethod
    def wrap(value: object) -> list[Any]:
        """Normalize ``None``/scalar/tuple to a list. Returns list[Any] by design."""
        if value is None:
            return []
        if isinstance(value, list | tuple):
            seq = cast("Sequence[Any]", value)
            return list(seq)
        return [value]

    @staticmethod
    def prepend(items: Sequence[T], value: T) -> list[T]:
        return [value, *items]

    @staticmethod
    def where(items: Iterable[T], predicate: Callable[[T], bool]) -> list[T]:
        return [item for item in items if predicate(item)]

    # ── shuffle ────────────────────────────────────────────────────────

    @staticmethod
    def shuffle(items: Sequence[T]) -> list[T]:
        """Cryptographically secure shuffle. For deterministic shuffles use ``random.Random``."""
        out = list(items)
        # Fisher-Yates with secrets.randbelow — no PRNG seed, no biased ranges
        for i in range(len(out) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            out[i], out[j] = out[j], out[i]
        return out

    # ── divide ─────────────────────────────────────────────────────────

    @staticmethod
    def divide(data: Mapping[T, V]) -> tuple[list[T], list[V]]:
        return list(data.keys()), list(data.values())


__all__ = ["Arr"]
