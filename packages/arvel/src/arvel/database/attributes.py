"""Accessor and mutator decorators (computed read / transformed write)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

T = TypeVar("T")


def accessor(fn: Callable[[Any], T]) -> property:
    """Decorate a method ``def full_name(self) -> str: ...`` as a read-only property.

    Equivalent to ``@property`` with a marker (``__arvel_accessor__ = True``)
    so introspection (``to_dict``, schema diffing) can distinguish accessors
    from raw columns.
    """
    prop = property(fn)
    cast("Any", fn).__arvel_accessor__ = True
    return prop


def mutator(column: str) -> Callable[[Callable[[Any, Any], Any]], Callable[[Any, Any], Any]]:
    """Decorate a function that transforms a value before storing to ``column``.

    Usage::

        @mutator("password")
        def set_password(self, value: str) -> str:
            return hash_password(value)

    The model metaclass collects mutators in ``__init_subclass__`` and applies
    them in ``__setattr__``, so ``Model(password=raw)`` and ``m.password = raw``
    both run the transform. None values are passed through untouched. The
    function stays a plain callable, so tests can invoke it directly.
    """

    def decorator(fn: Callable[[Any, Any], Any]) -> Callable[[Any, Any], Any]:
        marker = cast("Any", fn)
        marker.__arvel_mutator__ = True
        marker.__arvel_mutator_column__ = column
        return fn

    return decorator


__all__ = ["accessor", "mutator"]
