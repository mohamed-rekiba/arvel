"""Local and global query scopes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, ParamSpec, Protocol, TypeGuard, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Callable

    from arvel.database.model import Model
    from arvel.database.query import QueryBuilder

T = TypeVar("T", bound="Model")
P = ParamSpec("P")
R_co = TypeVar("R_co", covariant=True)
R = TypeVar("R")


class _ScopeFn(Protocol[P, R_co]):
    """Protocol for a ``@scope``-decorated function: first arg is the QB."""

    @staticmethod
    def __call__(qb: QueryBuilder[Any], *args: P.args, **kwargs: P.kwargs) -> R_co: ...


def _is_query_builder(value: Any) -> TypeGuard[QueryBuilder[Any]]:
    """TypeGuard for ``QueryBuilder[Any]`` that both mypy and pyright respect.

    Direct ``isinstance(x, QueryBuilder)`` inside generic callers narrows to
    ``QueryBuilder[Unknown]`` under pyright (the parameter is erased), which
    fires ``reportUnknownVariableType`` on every downstream use. A ``TypeGuard``
    returning ``QueryBuilder[Any]`` makes the narrowed type explicit and
    consistent across both checkers.
    """
    from arvel.database.query import QueryBuilder

    return isinstance(value, QueryBuilder)


class _ClassScopeCaller:
    """Callable returned from class-level scope access (``MyModel.my_scope``).

    Auto-creates a fresh ``QueryBuilder`` for ``model_cls`` when no QB is
    supplied as the first positional argument; otherwise forwards the supplied
    QB. Carries ``__arvel_scope__ = True`` so :class:`QueryBuilder.__getattr__`
    can detect that the attribute is a scope and forward calls accordingly.
    """

    __arvel_scope__: ClassVar[bool] = True

    def __init__(self, fn: Any, model_cls: type[Model]) -> None:
        self._fn = fn
        self._model_cls = model_cls

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        from arvel.database.query import QueryBuilder

        if args and _is_query_builder(args[0]):
            return self._fn(args[0], *args[1:], **kwargs)
        return self._fn(QueryBuilder(self._model_cls), *args, **kwargs)


class _ScopeDescriptor:
    """Non-data descriptor wrapping a ``@scope`` function.

    Class-level access (``MyModel.my_scope(arg)``) auto-creates a fresh
    QueryBuilder for the model and passes it as the first argument — mirroring
    Laravel's ``__callStatic`` injection of ``$query``.

    Instance-level QB access (``Model.my_scope(arg)``) is dispatched by
    :class:`~arvel.database.query.QueryBuilder.__getattr__`, which detects this
    descriptor and calls the wrapped function with the live builder.
    """

    def __init__(self, fn: Any) -> None:
        # Stack-friendly: unwrap ``@staticmethod`` so the runtime function is
        # always a plain callable regardless of decorator stacking.
        if isinstance(fn, staticmethod):
            fn = fn.__func__
        self._fn = fn
        self.__arvel_scope__ = True
        self.__name__ = getattr(fn, "__name__", repr(fn))
        self.__doc__ = getattr(fn, "__doc__", None)

    def __get__(self, obj: Any, cls: type | None = None) -> Any:
        if cls is None:
            return self
        if obj is None:
            return _ClassScopeCaller(self._fn, cast("type[Model]", cls))
        return self._fn.__get__(obj, cls)

    def __set_name__(self, owner: type, name: str) -> None:
        self.__name__ = name


# Type-checker view: ``scope`` consumes a :class:`_ScopeFn` (a callable whose
# first argument is the query builder, modelled as a Protocol with a
# ``@staticmethod`` ``__call__`` so type checkers do not flag a missing
# ``self``). It returns a plain ``Callable`` whose first parameter has been
# dropped — callers see only the user-supplied arguments.
#
# Runtime view: ``scope`` returns :class:`_ScopeDescriptor`, which implements
# the Laravel-style auto-QB injection on class-level access. The descriptor
# transparently unwraps :class:`staticmethod` so users stack ``@scope`` /
# ``@staticmethod`` without runtime ceremony.
if TYPE_CHECKING:

    def scope(fn: _ScopeFn[P, R]) -> Callable[P, R]:
        """Decorator marking a function as a local query scope.

        Stack with ``@staticmethod`` so type checkers do not treat the
        wrapped function as a regular method. The first parameter must be a
        :class:`~arvel.database.query.QueryBuilder`; the framework injects
        it on class-level access. The resulting callable exposes only the
        user-supplied parameters::

            class User(Model):
                @scope
                @staticmethod
                def active(qb: QueryBuilder["User"]) -> QueryBuilder["User"]:
                    return qb.where(User.status == "active")

            User.active()  # type-checks; QB is injected at runtime
        """
        ...

else:

    def scope(fn: Any) -> _ScopeDescriptor:
        """Decorator marking a function as a local query scope.

        The decorated function must accept ``(qb, *args, **kwargs)`` and return
        a :class:`~arvel.database.query.QueryBuilder`. Supports two call
        styles::

            User.active()            # class-level: auto-creates QB
            User.active()   # QB-level: forwards via QB.__getattr__
        """
        return _ScopeDescriptor(fn)


class GlobalScope(ABC):
    """Base class for global scopes applied to every query on a model.

    Register at class definition time via ``__arvel_global_scopes__`` or at
    runtime via :meth:`arvel.database.Model.add_global_scope` — both accept a
    ``GlobalScope`` instance or a raw callable.
    """

    @abstractmethod
    def apply(self, qb: QueryBuilder[Any]) -> QueryBuilder[Any]:
        """Return a new QueryBuilder with the scope applied."""


class SoftDeleteScope(GlobalScope):
    """Hides soft-deleted rows from default queries.

    The :class:`~arvel.database.SoftDeletes` mixin registers an instance of
    this scope on every concrete subclass. Bypass it with
    ``Model.query().with_trashed()`` or ``.only_trashed()``.
    """

    def __init__(self, column: str = "deleted_at") -> None:
        self.column = column

    def apply(self, qb: QueryBuilder[Any]) -> QueryBuilder[Any]:
        col = getattr(qb.model, self.column, None)
        if col is None or not hasattr(col, "is_"):
            return qb
        return qb.where(col.is_(None))


__all__ = ["GlobalScope", "SoftDeleteScope", "_ScopeDescriptor", "scope"]
