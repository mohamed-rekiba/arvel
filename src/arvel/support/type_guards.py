"""Type guard functions for safe runtime type narrowing.

These replace ``isinstance + issubclass`` patterns with functions that
inform type checkers about the narrowed type after the guard passes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeGuard

if TYPE_CHECKING:
    from arvel.data.model import ArvelModel
    from arvel.data.repository import Repository


def is_arvel_model(cls: type) -> TypeGuard[type[ArvelModel]]:
    """True if *cls* is a concrete subclass of ``ArvelModel``."""
    from arvel.data.model import ArvelModel

    return isinstance(cls, type) and issubclass(cls, ArvelModel)


def is_repository(obj: Any) -> TypeGuard[Repository[Any]]:
    """True if *obj* is an instance of ``Repository``."""
    from arvel.data.repository import Repository

    return isinstance(obj, Repository)


def is_table_model(cls: type) -> TypeGuard[type[ArvelModel]]:
    """True if *cls* is an ``ArvelModel`` subclass with ``__tablename__``."""
    from arvel.data.model import ArvelModel

    return isinstance(cls, type) and issubclass(cls, ArvelModel) and hasattr(cls, "__tablename__")
