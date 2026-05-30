"""``column_attr`` — ``@declared_attr`` wrapper that auto-injects ``Mapped[T]``.

Kept in its own module so both ``orm/__init__.py`` and ``orm/relations.py`` can
import it without creating a circular dependency.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from sqlalchemy.orm import Mapped, declared_attr

_T = TypeVar("_T")
_MappedAlias: Any = Mapped


def column_attr(fn: Callable[..., _T]) -> declared_attr[_T]:
    """``@declared_attr`` variant that accepts plain return types instead of ``Mapped[T]``.

    Wraps the return annotation in ``Mapped[T]`` automatically, so abstract mixins
    shared across multiple concrete mappers can declare columns without importing
    ``Mapped``::

        class ProductBase:
            @column_attr
            def id(self) -> uuid.UUID:          # plain type — no Mapped needed
                return uuid_id()

            @column_attr
            def category(self) -> Category | None:
                return relationship("Category", ...)

    Works with or without ``from __future__ import annotations``. ``Mapped`` is
    injected into the defining module's namespace automatically so ``get_type_hints``
    can resolve the wrapped string annotation.
    """
    fn_any: Any = fn
    ret = fn_any.__annotations__.get("return")
    if ret is not None:
        # Ensure Mapped is resolvable in the calling module when get_type_hints()
        # evaluates the string annotation produced by __future__.annotations.
        fn_any.__globals__.setdefault("Mapped", Mapped)
        if isinstance(ret, str):
            if not ret.startswith("Mapped["):
                fn_any.__annotations__["return"] = f"Mapped[{ret}]"
        elif getattr(ret, "__origin__", None) is not Mapped:
            fn_any.__annotations__["return"] = _MappedAlias[ret]
    return cast("declared_attr[_T]", declared_attr(fn_any))


__all__ = ["column_attr"]
