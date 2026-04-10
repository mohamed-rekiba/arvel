"""Query scopes — reusable, composable query constraints.

Local scopes are defined as ``scope_*`` methods on models and become
chainable methods on the query builder.  Global scopes are applied
automatically to every query on the model unless explicitly excluded.

Example::

    class User(ArvelModel):
        __tablename__ = "users"

        @scope
        @staticmethod
        def active(query: QueryBuilder[User]) -> QueryBuilder[User]:
            return query.where(User.is_active == True)

        @scope
        @staticmethod
        def older_than(query: QueryBuilder[User], age: int) -> QueryBuilder[User]:
            return query.where(User.age > age)

    # Usage:
    users = await User.query(session).active().older_than(30).all()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from arvel.data.query import QueryBuilder

_SCOPE_ATTR = "__arvel_scope__"
_GLOBAL_SCOPE_REGISTRY_ATTR = "__global_scopes__"
_SCOPE_REGISTRY_ATTR = "__scope_registry__"


def scope(fn: Any) -> Any:
    """Mark a static/classmethod as a local query scope.

    The decorator sets a marker attribute; ``__init_subclass__`` picks it
    up and registers the scope name (stripped of the ``scope_`` prefix if
    present).

    Works with both bare functions and ``@staticmethod``/``@classmethod``
    wrappers regardless of decorator order.
    """
    if isinstance(fn, staticmethod):
        setattr(fn.__func__, _SCOPE_ATTR, True)
        return fn
    if isinstance(fn, classmethod):
        setattr(fn.__func__, _SCOPE_ATTR, True)
        return fn
    setattr(fn, _SCOPE_ATTR, True)
    return fn


class GlobalScope:
    """Base class for global scopes applied to every query on a model.

    Subclass and implement ``apply`` to define the constraint::

        class ActiveScope(GlobalScope):
            def apply(self, query):
                return query.where(User.is_active == True)

        class User(ArvelModel):
            __global_scopes__ = [ActiveScope()]
    """

    name: str = ""

    def apply(self, query: QueryBuilder[Any]) -> QueryBuilder[Any]:
        """Apply the scope to the given query builder. Must return the query."""
        raise NotImplementedError

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.name:
            cls.name = cls.__name__


class ScopeRegistry:
    """Stores local and global scopes for a model class."""

    def __init__(self) -> None:
        self._local: dict[str, Callable[..., Any]] = {}
        self._global: list[GlobalScope] = []

    def register_local(self, name: str, fn: Callable[..., Any]) -> None:
        self._local[name] = fn

    def register_global(self, scope_instance: GlobalScope) -> None:
        self._global.append(scope_instance)

    def get_local(self, name: str) -> Callable[..., Any] | None:
        return self._local.get(name)

    def get_globals(self) -> list[GlobalScope]:
        return list(self._global)

    def local_names(self) -> set[str]:
        return set(self._local.keys())


def _discover_scopes(cls: type) -> ScopeRegistry:
    """Walk a model class and register all scope-decorated methods."""
    registry = ScopeRegistry()

    for attr_name in dir(cls):
        # Use __dict__ traversal to find scope markers on wrapped functions
        raw = cls.__dict__.get(attr_name)
        if raw is None:
            # Also check parent classes
            for base in cls.__mro__[1:]:
                raw = base.__dict__.get(attr_name)
                if raw is not None:
                    break

        if raw is None:
            continue

        fn = raw
        if isinstance(fn, (staticmethod, classmethod)):
            fn = fn.__func__

        if getattr(fn, _SCOPE_ATTR, False):
            scope_name = (
                attr_name.removeprefix("scope_") if attr_name.startswith("scope_") else attr_name
            )
            resolved = getattr(cls, attr_name)
            registry.register_local(scope_name, resolved)

    global_scopes: list[GlobalScope] = getattr(cls, _GLOBAL_SCOPE_REGISTRY_ATTR, [])
    for gs in global_scopes:
        registry.register_global(gs)

    return registry
