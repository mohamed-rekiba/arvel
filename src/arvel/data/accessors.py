"""Attribute accessors and mutators for ArvelModel.

Accessors compute a value on read (virtual attributes).
Mutators transform a value on write.

Usage::

    class User(ArvelModel):
        __tablename__ = "users"
        first_name: Mapped[str] = mapped_column(String(100))
        last_name: Mapped[str] = mapped_column(String(100))

        @accessor("full_name")
        def get_full_name(self) -> str:
            return f"{self.first_name} {self.last_name}"

        @mutator("password")
        def set_password(self, value: str) -> str:
            return bcrypt.hash(value)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

_ACCESSOR_REGISTRY_ATTR = "__accessor_registry__"
_MUTATOR_REGISTRY_ATTR = "__mutator_registry__"

_ACCESSOR_ATTR = "__arvel_accessors__"
_MUTATOR_ATTR = "__arvel_mutators__"


def accessor(attr_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to register a method as an accessor for *attr_name*."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        names: list[str] = getattr(fn, _ACCESSOR_ATTR, [])
        if not names:
            object.__setattr__(fn, _ACCESSOR_ATTR, names)
        names.append(attr_name)
        return fn

    return decorator


def mutator(attr_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to register a method as a mutator for *attr_name*."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        names: list[str] = getattr(fn, _MUTATOR_ATTR, [])
        if not names:
            object.__setattr__(fn, _MUTATOR_ATTR, names)
        names.append(attr_name)
        return fn

    return decorator


class AccessorRegistry:
    """Stores accessor and mutator mappings for a model class."""

    def __init__(self) -> None:
        self._accessors: dict[str, Callable[..., Any]] = {}
        self._mutators: dict[str, Callable[..., Any]] = {}

    def register_accessor(self, attr_name: str, fn: Callable[..., Any]) -> None:
        self._accessors[attr_name] = fn

    def register_mutator(self, attr_name: str, fn: Callable[..., Any]) -> None:
        self._mutators[attr_name] = fn

    def get_accessor(self, attr_name: str) -> Callable[..., Any] | None:
        return self._accessors.get(attr_name)

    def get_mutator(self, attr_name: str) -> Callable[..., Any] | None:
        return self._mutators.get(attr_name)

    def accessor_names(self) -> set[str]:
        return set(self._accessors.keys())

    def mutator_names(self) -> set[str]:
        return set(self._mutators.keys())


def _discover_accessors(cls: type) -> AccessorRegistry:
    """Walk a model class and register accessor/mutator methods."""
    registry = AccessorRegistry()

    for attr_name in dir(cls):
        obj = getattr(cls, attr_name, None)
        if obj is None:
            continue

        accessor_attrs: list[str] = getattr(obj, _ACCESSOR_ATTR, [])
        for acc_name in accessor_attrs:
            registry.register_accessor(acc_name, obj)

        mutator_attrs: list[str] = getattr(obj, _MUTATOR_ATTR, [])
        for mut_name in mutator_attrs:
            registry.register_mutator(mut_name, obj)

    return registry
