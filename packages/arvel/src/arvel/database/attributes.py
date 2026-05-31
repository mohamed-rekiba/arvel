"""Accessor and mutator decorators (computed read / transformed write)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import Any, TypeVar, cast

T = TypeVar("T")

_ATTR_CACHE = "_arvel_attr_cache"


class Attribute:
    """Symmetric `get`/`set` for one virtual attribute (Laravel's ``Attribute``).

    Define a single class attribute that routes both reads and writes through
    one descriptor — handy for computed values backed by several columns::

        class User(Model):
            first_name: str = string(50)
            last_name: str = string(50)

            full_name = Attribute.make(
                get=lambda m: f"{m.first_name} {m.last_name}",
                set=lambda m, v: dict(zip(("first_name", "last_name"), v.split(" ", 1))),
            )

    ``get`` takes the model and returns the computed value. ``set`` takes
    ``(model, value)`` and returns a ``Mapping`` of real column names to write
    (each routed through normal casts/mutators). ``should_cache()`` memoizes the
    computed value per instance until the next write through this attribute.
    """

    def __init__(
        self,
        *,
        get: Callable[[Any], Any] | None = None,
        set: Callable[[Any, Any], Any] | None = None,  # noqa: A002 — mirrors Laravel's API
        cached: bool = False,
    ) -> None:
        self._getter = get
        self._setter = set
        self.cached = cached
        self.name = ""

    @classmethod
    def make(
        cls,
        *,
        get: Callable[[Any], Any] | None = None,
        set: Callable[[Any, Any], Any] | None = None,  # noqa: A002 — mirrors Laravel's API
    ) -> Attribute:
        return cls(get=get, set=set)

    def should_cache(self) -> Attribute:
        self.cached = True
        return self

    def __set_name__(self, _owner: type[Any], name: str) -> None:
        self.name = name

    def __get__(self, instance: Any, _owner: type[Any] | None = None) -> Any:
        if instance is None:
            return self
        if self._getter is None:
            raise AttributeError(f"{self.name!r} is write-only.")
        if self.cached:
            store = self._cache(instance)
            if self.name in store:
                return store[self.name]
            value = self._getter(instance)
            store[self.name] = value
            return value
        return self._getter(instance)

    def __set__(self, instance: Any, value: Any) -> None:
        if self._setter is None:
            raise AttributeError(f"{self.name!r} is read-only.")
        result = self._setter(instance, value)
        if not isinstance(result, Mapping):
            raise TypeError(
                f"Attribute {self.name!r} setter must return a mapping of "
                f"column->value, got {type(result).__name__}."
            )
        columns = cast("Mapping[str, Any]", result)
        for column, column_value in columns.items():
            setattr(instance, column, column_value)
        if self.cached:
            self._cache(instance).pop(self.name, None)

    @staticmethod
    def _cache(instance: Any) -> dict[str, Any]:
        store: dict[str, Any] | None = instance.__dict__.get(_ATTR_CACHE)
        if store is None:
            store = {}
            object.__setattr__(instance, _ATTR_CACHE, store)
        return store


class CastsAttributes(ABC):
    """Attribute-level custom cast: route a column's reads/writes through get/set.

    Register the class or an instance in ``__casts__``::

        class AsUpper(CastsAttributes):
            def get(self, model, key, value) -> str:
                return value.upper()

            def set(self, model, key, value) -> str:
                return value.lower()

        class Doc(Model):
            __casts__ = {"code": AsUpper}   # or AsUpper()
    """

    @abstractmethod
    def get(self, model: Any, key: str, value: Any) -> Any:
        """Transform the stored value on read."""

    @abstractmethod
    def set(self, model: Any, key: str, value: Any) -> Any:
        """Transform the in-memory value before it's stored."""

    def serialize(self, model: Any, key: str, value: Any) -> Any:
        """Form used by ``to_dict()``; defaults to the get value unchanged."""
        return value


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


__all__ = ["Attribute", "CastsAttributes", "accessor", "mutator"]
