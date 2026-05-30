"""Module-level registry of ArvelSettings subclasses.

Populated by ``@register`` (and by ``Application.with_config_files([...])``).
Consumed by ``ConfigServiceProvider`` to bind each class as a singleton.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arvel.config.settings import ArvelSettings


_REGISTERED: list[type[ArvelSettings]] = []


def register(cls: type[ArvelSettings]) -> type[ArvelSettings]:
    """Mark a config class for auto-registration. Usable as a decorator."""
    if cls not in _REGISTERED:
        _REGISTERED.append(cls)
    return cls


def registered_configs() -> Iterable[type[ArvelSettings]]:
    return list(_REGISTERED)


def clear() -> None:
    """Test helper — reset registry between tests."""
    _REGISTERED.clear()


def unregister(cls: type[ArvelSettings]) -> None:
    """Test helper — remove a single class from the registry without affecting others.

    Used by tests that register a hostile or throwaway config to avoid leaking
    it into the rest of the suite. Idempotent.
    """
    if cls in _REGISTERED:
        _REGISTERED.remove(cls)
