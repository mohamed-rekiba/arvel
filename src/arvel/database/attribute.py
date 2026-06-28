"""arvel.database.attribute — the Laravel L9+ ``Attribute`` accessor/mutator API.

A model method returning ``Attribute(get=, set=, cached=)`` is discovered by ``ModelMeta``
and consulted in ``_cast_get``/``_cast_set``. ``get``/``set`` are callables taking
``(value, attributes)``. Grounded in knowledge/port/07-orm-active-record.md.
"""

from __future__ import annotations

from typing import Any


class Attribute:
    """An accessor/mutator definition for a model attribute."""

    def __init__(self, *, get: Any = None, set: Any = None, cached: bool = False) -> None:
        self.get = get
        self.set = set
        self.cached = cached


def returns_attribute(func: Any) -> bool:
    """True if ``func`` is annotated to return an ``Attribute`` (accessor/mutator method)."""
    annotation = getattr(func, "__annotations__", {}).get("return")
    if annotation is None:
        return False
    if isinstance(annotation, str):
        return annotation.split(".")[-1] == "Attribute"
    return getattr(annotation, "__name__", None) == "Attribute"


__all__ = ["Attribute", "returns_attribute"]
