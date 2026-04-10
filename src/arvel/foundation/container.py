"""Lightweight DI container — scoped resolution with constructor injection.

Provides APP/REQUEST/SESSION lifetime scopes, interface-to-concrete binding,
factory bindings, and automatic constructor parameter injection.
"""

from __future__ import annotations

import inspect
from collections.abc import (
    Callable,  # noqa: TC003 - needed at runtime for get_type_hints resolution
)
from enum import Enum
from functools import lru_cache
from types import MappingProxyType
from typing import Annotated, Any, cast, get_args, get_origin, get_type_hints

from arvel.foundation.exceptions import DependencyError


class Scope(Enum):
    """DI lifetime scopes.

    APP — singleton for the application lifetime.
    REQUEST — fresh instance per HTTP request.
    SESSION — shared within a user session across requests.
    """

    APP = "app"
    REQUEST = "request"
    SESSION = "session"


class _SentinelType:
    pass


_SENTINEL = _SentinelType()


class _Binding:
    __slots__ = ("concrete", "factory", "interface", "is_value", "scope", "value")

    def __init__(
        self,
        interface: type,
        *,
        concrete: type | None = None,
        factory: Callable[[], object] | None = None,
        value: object = _SENTINEL,
        scope: Scope,
    ) -> None:
        self.interface = interface
        self.concrete = concrete
        self.factory = factory
        self.value = value
        self.scope = scope
        self.is_value = value is not _SENTINEL


class ContainerBuilder:
    """Collects bindings during the register phase."""

    def __init__(self) -> None:
        self._bindings: list[_Binding] = []

    def provide[T](
        self,
        interface: type[T],
        concrete: type[T],
        scope: Scope = Scope.REQUEST,
    ) -> None:
        self._bindings.append(_Binding(interface, concrete=concrete, scope=scope))

    def provide_factory[T](
        self,
        interface: type[T],
        factory: Callable[[], T],
        scope: Scope = Scope.REQUEST,
    ) -> None:
        self._bindings.append(_Binding(interface, factory=factory, scope=scope))

    def provide_value[T](
        self,
        interface: type[T],
        value: T,
        scope: Scope = Scope.APP,
    ) -> None:
        self._bindings.append(_Binding(interface, value=value, scope=scope))

    def build(self) -> Container:
        bindings_map: dict[type, _Binding] = {}
        for b in self._bindings:
            bindings_map[b.interface] = b
        return Container(bindings_map, scope=Scope.APP)


class Container:
    """Resolved DI container — provides typed dependency resolution."""

    def __init__(
        self,
        bindings: dict[type, _Binding],
        scope: Scope,
        parent: Container | None = None,
    ) -> None:
        self._bindings = bindings
        self._scope = scope
        self._parent = parent
        self._instances: dict[
            type, Any
        ] = {}  # type-erased storage; resolve() restores T via type[T] key
        self._closed = False

    async def resolve[T](self, interface: type[T]) -> T:
        if self._closed:
            raise DependencyError(
                f"Container is closed, cannot resolve {interface.__name__}",
                requested_type=interface,
            )

        if interface in self._instances:
            return self._instances[interface]

        binding = self._bindings.get(interface)
        if binding is None:
            if self._parent is not None:
                return await self._parent.resolve(interface)
            raise DependencyError(
                f"No binding registered for {interface.__name__}",
                requested_type=interface,
            )

        if binding.is_value:
            self._instances[interface] = binding.value
            # Sound cast: provide_value(type[T], T) guarantees value is T
            return cast("T", binding.value)

        if binding.scope == Scope.APP and self._scope != Scope.APP and self._parent:
            return await self._parent.resolve(interface)

        if binding.scope == Scope.SESSION and self._scope == Scope.REQUEST and self._parent:
            return await self._parent.resolve(interface)

        instance = await self._create_instance(binding)
        self._instances[interface] = instance
        return cast("T", instance)

    async def _create_instance(self, binding: _Binding) -> object:
        if binding.factory is not None:
            return binding.factory()
        if binding.concrete is not None:
            return await self._construct_with_injection(binding.concrete)
        raise DependencyError(
            f"No concrete or factory for {binding.interface.__name__}",
            requested_type=binding.interface,
        )

    async def _construct_with_injection(self, cls: type) -> object:
        """Instantiate *cls* by resolving constructor parameters from the container.

        Falls back to no-arg construction when the class has no typed
        constructor parameters (e.g. default ``object.__init__``).
        """
        hints = self._get_init_hints(cls)
        if hints is None:
            return cls()

        sig = inspect.signature(cls.__init__)
        kwargs: dict[str, Any] = {}
        for name, param in sig.parameters.items():
            if name == "self" or param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            await self._resolve_param(cls, name, param, hints, kwargs)
        return cls(**kwargs)

    @staticmethod
    @lru_cache(maxsize=128)
    def _get_init_hints(cls: type) -> MappingProxyType[str, Any] | None:
        """Return type hints for *cls.__init__*, or None if no injection needed.

        Cached per class — constructor signatures don't change at runtime.
        Returns a read-only view to prevent accidental mutation of the cache.
        """
        if cls.__init__ is object.__init__:
            return None
        try:
            hints = get_type_hints(cls.__init__, include_extras=True)
        except Exception:
            return None
        hints.pop("return", None)
        return MappingProxyType(hints) if hints else None

    async def _resolve_param(
        self,
        cls: type,
        name: str,
        param: inspect.Parameter,
        hints: MappingProxyType[str, Any],
        out: dict[str, Any],
    ) -> None:
        hint = hints.get(name)
        if hint is None:
            if param.default is inspect.Parameter.empty:
                raise DependencyError(
                    f"Cannot resolve parameter '{name}' of {cls.__name__}: no type hint",
                    requested_type=cls,
                )
            return

        if get_origin(hint) is Annotated:
            hint = get_args(hint)[0]

        try:
            out[name] = await self.resolve(hint)
        except DependencyError as exc:
            if param.default is inspect.Parameter.empty:
                hint_name = getattr(hint, "__name__", str(hint))
                raise DependencyError(
                    f"Cannot resolve parameter '{name}: {hint_name}' of {cls.__name__}",
                    requested_type=cls,
                ) from exc

    def instance[T](self, interface: type[T], value: T) -> None:
        """Register a pre-built instance at runtime (post-boot).

        Use sparingly — prefer ``ContainerBuilder.provide_factory`` during
        ``register()``.  This exists for services assembled during ``boot()``
        that depend on other resolved services.
        """
        self._instances[interface] = value

    async def enter_scope(self, scope: Scope) -> Container:
        return Container(dict(self._bindings), scope=scope, parent=self)

    async def close(self) -> None:
        self._closed = True
        self._instances.clear()
