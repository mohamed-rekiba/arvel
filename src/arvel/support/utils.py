"""Type-safe nested data access for dicts, lists, and objects.

``data_get`` walks a dot-separated path through nested structures,
returning a typed default when any segment is missing. Numeric
segments are used as list indices when the current value is a
``Sequence`` (but not ``str``/``bytes``).

Examples::

    data_get({"a": {"b": 1}}, "a.b")              # 1
    data_get({"items": [{"id": 10}]}, "items.0.id")  # 10
    data_get({}, "missing.key", "fallback")        # "fallback"
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, overload

_MISSING = object()


@overload
def data_get(data: Any, path: str) -> Any: ...


@overload
def data_get[T](data: Any, path: str, default: T) -> T: ...


def data_get(data: Any, path: str, default: Any = None) -> Any:
    """Walk *path* (dot-separated) into a nested dict/list/object.

    Each segment is tried in order:

    1. ``dict.__getitem__``  — if *current* is a ``dict``
    2. ``list.__getitem__``  — if *current* is a non-str ``Sequence`` and
       *segment* looks like an integer
    3. ``getattr``           — as a final object-attribute fallback

    Returns *default* the moment any segment cannot be resolved.
    """
    if not path:
        return data

    current: Any = data
    for segment in path.split("."):
        if current is None:
            return default

        current = _resolve_segment(current, segment, _MISSING)
        if current is _MISSING:
            return default

    return current


def _resolve_segment(current: Any, segment: str, missing: object) -> Any:
    """Resolve a single path segment against the current value."""
    if isinstance(current, dict):
        return current.get(segment, missing)

    if isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
        try:
            return current[int(segment)]
        except ValueError, IndexError:
            return missing

    result: Any = getattr(current, segment, missing)
    return result


def to_snake_case(name: str) -> str:
    """Convert PascalCase or camelCase to snake_case."""
    import re

    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def pluralize(name: str) -> str:
    """Naive English pluralization."""
    if name.endswith("y") and not name.endswith(("ay", "ey", "oy", "uy")):
        return name[:-1] + "ies"
    if name.endswith(("s", "sh", "ch", "x", "z")):
        return name + "es"
    return name + "s"
