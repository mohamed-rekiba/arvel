"""Auto-wiring DI container with scopes, contextual bindings, tagging, and extensions."""

from __future__ import annotations

import asyncio
import inspect
import weakref
from collections.abc import (
    AsyncGenerator,
    Awaitable,
    Callable,
    Generator,
    Iterable,
)
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any, TypeVar, cast, get_origin, get_type_hints

from arvel.container.errors import (
    AsyncBindingError,
    BindingResolutionError,
    CircularDependencyError,
)
from arvel.container.inspect import (
    init_hints,
    is_async_callable,
    is_concrete_class,
    optional_init_params,
)
from arvel.container.scopes import Scope

T = TypeVar("T")

# Distinguishes "no contextual binding" from a contextual value that is itself
# falsy/None, so the parent-scope walk in _find_contextual can't be fooled.
_MISSING: Any = object()


def _get_method_hints(fn: Any) -> dict[str, Any]:
    """Extract type hints from a method.

    Python 3.14 (PEP 649) returns string annotations from __annotations__ for
    locally-scoped types. We try get_type_hints first, then fall back to the
    raw __annotations__ dict (which may contain strings or actual types).
    """
    try:
        hints = get_type_hints(fn)
    except Exception:  # noqa: BLE001 — unresolvable local types (e.g. PEP-649 closures)
        underlying = getattr(fn, "__func__", fn)
        hints = dict(getattr(underlying, "__annotations__", {}))
    hints.pop("return", None)
    return hints


# Represents any class or callable that can serve as a container key or concrete.
# Using Callable[..., Any] instead of `type` alone accepts abstract classes and
# Protocols without forcing callers to add `# type: ignore[type-abstract]`.
type AbstractKey = type | Callable[..., Any]

# A binding's concrete is either a class (auto-wire its __init__), a sync callable, or an
# async callable.
Concrete = AbstractKey | Callable[..., Awaitable[Any]]
Decorator = Callable[[Any, "Container"], Any]


@dataclass(slots=True)
class _Binding:
    abstract: AbstractKey
    concrete: Concrete
    scope: Scope
    is_async: bool


class _ContextualGive:
    __slots__ = ("_consumer", "_container", "_dep")

    def __init__(self, container: Container, consumer: type, dep: type) -> None:
        self._container = container
        self._consumer = consumer
        self._dep = dep

    def give(self, concrete: AbstractKey | object) -> None:
        self._container._register_contextual(  # pyright: ignore[reportPrivateUsage]
            self._consumer, self._dep, concrete
        )


class ContextualBuilder:
    __slots__ = ("_consumer", "_container")

    def __init__(self, container: Container, consumer: type) -> None:
        self._container = container
        self._consumer = consumer

    def needs(self, dependency: type[T]) -> _ContextualGive:
        return _ContextualGive(self._container, self._consumer, dependency)


class Container:
    """The DI container."""

    def __init__(self, *, parent: Container | None = None) -> None:
        self._parent = parent

        # The root container is the only one that holds singleton/instance caches.
        if parent is None:
            self._singletons: dict[type, Any] = {}
            self._instances: dict[type, Any] = {}
        else:
            self._singletons = parent._singletons
            self._instances = parent._instances

        # Bindings: in scopes, fall through to parent bindings.
        self._bindings: dict[AbstractKey, _Binding] = {}
        self._contextual: dict[tuple[type, type], Any] = {}
        self._tags: dict[str, list[type]] = {}
        self._extensions: dict[type, list[Decorator]] = {}

        # Per-scope cache; only used when this container is a scope.
        self._scope_cache: dict[type, Any] = {}

        # Open child scopes, so a rebind here can also drop their stale scoped
        # instances. Weak so an abandoned scope doesn't keep the child alive.
        self._children: weakref.WeakSet[Container] = weakref.WeakSet()

        # Per-abstract build locks for concurrent async resolution of shared
        # scopes; (loop, lock) so a container reused across loops re-locks.
        self._async_locks: dict[AbstractKey, tuple[asyncio.AbstractEventLoop, asyncio.Lock]] = {}

        # Bind self so make(Container) works.
        if parent is None:
            self._instances[Container] = self

    # ───────────────────────── Registration ──────────────────────────

    def bind(
        self,
        abstract: type[T] | Callable[..., T],
        concrete: type[T] | Callable[..., T] | Callable[..., Awaitable[T]] | None = None,
        *,
        scope: Scope = Scope.TRANSIENT,
    ) -> None:
        # abstract must be a type at runtime (used as a registry key); the
        # Callable[..., T] union lets callers pass abstract classes and Protocols
        # without a `# type: ignore[type-abstract]` at every binding site.
        impl: Concrete = concrete if concrete is not None else abstract
        if not callable(impl):
            msg = f"bind({abstract!r}, ...): concrete must be a class or callable."  # type: ignore[unreachable]
            raise TypeError(msg)
        is_async = is_async_callable(impl) if not is_concrete_class(impl) else False
        self._bindings[abstract] = _Binding(abstract, impl, scope, is_async)
        # Laravel's dropStaleInstances: a re-bind must not keep serving the
        # instance built from the previous binding. Caches are type-keyed; a
        # non-type abstract (a bare callable) was never cached.
        if isinstance(abstract, type):
            self._instances.pop(abstract, None)
            self._singletons.pop(abstract, None)
            self._scope_cache.pop(abstract, None)
            self._evict_scoped_in_descendants(abstract)

    def singleton(
        self,
        abstract: type[T] | Callable[..., T],
        concrete: type[T] | Callable[..., T] | Callable[..., Awaitable[T]] | None = None,
    ) -> None:
        self.bind(abstract, concrete, scope=Scope.SINGLETON)

    def scoped(
        self,
        abstract: type[T] | Callable[..., T],
        concrete: type[T] | Callable[..., T] | Callable[..., Awaitable[T]] | None = None,
    ) -> None:
        self.bind(abstract, concrete, scope=Scope.SCOPED)

    def bind_if(
        self,
        abstract: type[T] | Callable[..., T],
        concrete: type[T] | Callable[..., T] | Callable[..., Awaitable[T]] | None = None,
        *,
        scope: Scope = Scope.TRANSIENT,
    ) -> None:
        # Laravel's bindIf — register only when nothing is bound yet.
        if not self.bound(abstract):
            self.bind(abstract, concrete, scope=scope)

    def singleton_if(
        self,
        abstract: type[T] | Callable[..., T],
        concrete: type[T] | Callable[..., T] | Callable[..., Awaitable[T]] | None = None,
    ) -> None:
        self.bind_if(abstract, concrete, scope=Scope.SINGLETON)

    def scoped_if(
        self,
        abstract: type[T] | Callable[..., T],
        concrete: type[T] | Callable[..., T] | Callable[..., Awaitable[T]] | None = None,
    ) -> None:
        self.bind_if(abstract, concrete, scope=Scope.SCOPED)

    def instance(self, abstract: type[T], obj: T) -> None:
        self._instances[abstract] = obj

    # ───────────────────────── Advanced ──────────────────────────

    def when(self, consumer: type) -> ContextualBuilder:
        return ContextualBuilder(self, consumer)

    def _register_contextual(
        self, consumer: type, dep: type, concrete: AbstractKey | object
    ) -> None:
        self._contextual[(consumer, dep)] = concrete

    def tag(self, abstracts: Iterable[type], *tag_names: str) -> None:
        for name in tag_names:
            self._tags.setdefault(name, []).extend(abstracts)

    def tagged(self, tag_name: str) -> list[object]:
        # Heterogeneous by design — one tag groups unrelated types; callers narrow.
        return [self.make(abstract) for abstract in self._tags.get(tag_name, [])]

    def extend(self, abstract: type[T], decorator: Callable[[T, Container], T]) -> None:
        # A pre-built instance() can't be rebuilt, so (like Laravel) apply the
        # decorator to it right now and keep the result. Cached singleton/scoped
        # values are dropped instead so the decorator runs on the next make().
        if abstract in self._instances:
            self._instances[abstract] = decorator(self._instances[abstract], self)
        self._extensions.setdefault(abstract, []).append(decorator)
        self._singletons.pop(abstract, None)
        self._scope_cache.pop(abstract, None)
        self._evict_scoped_in_descendants(abstract)

    def _evict_scoped_in_descendants(self, abstract: type) -> None:
        # A rebind/extend on a parent must invalidate any scoped instance an
        # open child already cached, or the child keeps serving the stale one.
        for child in self._children:
            child._scope_cache.pop(abstract, None)
            child._evict_scoped_in_descendants(abstract)

    def _find_contextual(self, requestor: type, abstract: type) -> Any:
        # Walk the scope chain so contextual rules registered on a parent still
        # apply when resolving through a child scope (mirrors _find_binding).
        key = (requestor, abstract)
        container: Container | None = self
        while container is not None:
            if key in container._contextual:
                return container._contextual[key]
            container = container._parent
        return _MISSING

    # ───────────────────────── Resolution ──────────────────────────

    def make(self, abstract: type[T] | Callable[..., T], **overrides: object) -> T:
        # Mirror bind()'s key type: accepting Callable[..., T] lets callers resolve
        # an interface/Protocol they bound without a `# type: ignore[type-abstract]`.
        return self._resolve(
            cast("type[T]", abstract),
            overrides=overrides,
            path=(),
            requestor=None,
            allow_async=False,
        )

    async def amake(self, abstract: type[T] | Callable[..., T], **overrides: object) -> T:
        return await self._aresolve(
            cast("type[T]", abstract), overrides=overrides, path=(), requestor=None
        )

    def call(
        self,
        cls: type[Any],
        method: str,
        *,
        overrides: dict[str, object] | None = None,
    ) -> object:
        """Resolve *cls* from the container, then call *method* with injected params.

        Parameters are resolved from the container; *overrides* bypass injection
        for the specified parameter names. If *cls* is not bound, instantiates
        it directly (no-arg constructor assumed). The return is reflective — the
        caller knows the method's type and narrows.
        """
        try:
            instance: object = self.make(cls)
        except BindingResolutionError:
            instance = cls()
        fn = getattr(instance, method)
        raw_hints = _get_method_hints(fn)
        sig = inspect.signature(fn)
        kwargs: dict[str, Any] = dict(overrides or {})
        for param_name in sig.parameters:
            if param_name == "self":
                continue
            if param_name in kwargs:
                continue
            param_type = raw_hints.get(param_name)
            # Python 3.14 (PEP 649) may give string annotations for local types.
            # Resolve by matching the string name against bound types.
            if isinstance(param_type, str):
                param_type = next(
                    (t for t in self._bindings if t.__name__ == param_type),
                    None,
                )
            if isinstance(param_type, type) and self.bound(param_type):
                kwargs[param_name] = self.make(param_type)
        return fn(**kwargs)

    async def acall(
        self,
        cls: type[Any],
        method: str,
        *,
        overrides: dict[str, object] | None = None,
    ) -> object:
        """Async variant of call() — supports async methods and async-resolved deps."""
        try:
            instance: object = await self.amake(cls)
        except BindingResolutionError:
            instance = cls()
        fn = getattr(instance, method)
        raw_hints = _get_method_hints(fn)
        sig = inspect.signature(fn)
        kwargs: dict[str, Any] = dict(overrides or {})
        for param_name in sig.parameters:
            if param_name == "self":
                continue
            if param_name in kwargs:
                continue
            param_type = raw_hints.get(param_name)
            if isinstance(param_type, str):
                param_type = next(
                    (t for t in self._bindings if t.__name__ == param_type),
                    None,
                )
            if isinstance(param_type, type) and self.bound(param_type):
                kwargs[param_name] = await self.amake(param_type)
        if is_async_callable(fn):
            return await fn(**kwargs)
        return fn(**kwargs)

    # ───────────────────────── Introspection ──────────────────────────

    def bound(self, abstract: AbstractKey) -> bool:
        if abstract in self._bindings or abstract in self._instances:
            return True
        return self._parent is not None and self._parent.bound(abstract)

    def resolved(self, abstract: type) -> bool:
        return (
            abstract in self._singletons
            or abstract in self._instances
            or abstract in self._scope_cache
        )

    # ───────────────────────── Scopes ──────────────────────────

    @contextmanager
    def scope(self) -> Generator[Container]:
        child = Container(parent=self)
        self._children.add(child)
        try:
            yield child
        finally:
            child._scope_cache.clear()
            self._children.discard(child)

    @asynccontextmanager
    async def ascope(self) -> AsyncGenerator[Container]:
        child = Container(parent=self)
        self._children.add(child)
        try:
            yield child
        finally:
            child._scope_cache.clear()
            self._children.discard(child)

    # ───────────────────────── Internals ──────────────────────────

    def _find_binding(self, abstract: AbstractKey) -> _Binding | None:
        b = self._bindings.get(abstract)
        if b is not None:
            return b
        if self._parent is not None:
            return self._parent._find_binding(abstract)
        return None

    def _resolve(
        self,
        abstract: type[T],
        *,
        overrides: dict[str, object],
        path: tuple[type, ...],
        requestor: type | None,
        allow_async: bool,
    ) -> T:
        if not isinstance(abstract, type):  # pyright: ignore[reportUnnecessaryIsInstance]
            # Handle generic aliases like async_sessionmaker[AsyncSession] by
            # stripping type parameters and using the origin class for lookup.
            origin = get_origin(abstract)  # type: ignore[unreachable]
            if origin is None or not isinstance(origin, type):
                msg = f"make() requires a type, got {type(abstract).__name__!r}."
                raise TypeError(msg)
            abstract = origin

        if abstract in path:
            raise CircularDependencyError((*path, abstract))

        # Pre-built instance (highest priority).
        if abstract in self._instances:
            return cast("T", self._instances[abstract])

        # Contextual binding when there's a requestor (walks parent scopes).
        if requestor is not None:
            contextual = self._find_contextual(requestor, abstract)
            if contextual is not _MISSING:
                instance = self._invoke(contextual, abstract, path, allow_async=allow_async)
                return cast("T", self._apply_extensions(abstract, instance))

        binding = self._find_binding(abstract)

        if binding is not None:
            if binding.is_async and not allow_async:
                raise AsyncBindingError(abstract)

            # Singleton cache.
            if binding.scope is Scope.SINGLETON and abstract in self._singletons:
                return cast("T", self._singletons[abstract])

            # Scoped cache (only this container, not parent).
            if binding.scope is Scope.SCOPED and abstract in self._scope_cache:
                return cast("T", self._scope_cache[abstract])

            instance = self._invoke(
                binding.concrete,
                abstract,
                path,
                overrides=overrides,
                allow_async=allow_async,
            )
            instance = self._apply_extensions(abstract, instance)

            if binding.scope is Scope.SINGLETON:
                self._singletons[abstract] = instance
            elif binding.scope is Scope.SCOPED:
                self._scope_cache[abstract] = instance
            return cast("T", instance)

        # No binding — try auto-wire (only for concrete classes with explicit __init__).
        if inspect.isabstract(abstract):
            raise BindingResolutionError(
                (*path, abstract),
                reason="abstract not bound and not a concrete class",
            )

        # Treat classes without an explicit __init__ as interface/protocol-like
        # and refuse to silently instantiate them. The user must bind() them explicitly.
        if abstract.__init__ is object.__init__:
            raise BindingResolutionError(
                (*path, abstract),
                reason=(
                    f"{abstract.__qualname__} has no explicit __init__ "
                    f"and is not bound; call container.bind({abstract.__qualname__}, ...)"
                ),
            )

        instance = self._instantiate(abstract, overrides, abstract, path=path)
        return cast("T", self._apply_extensions(abstract, instance))

    def _instantiate(
        self,
        abstract: type[T],
        overrides: dict[str, object],
        requestor: type,
        *,
        path: tuple[type, ...] = (),
    ) -> T:
        hints = init_hints(abstract)
        optional = optional_init_params(abstract)
        kwargs: dict[str, Any] = {}
        for name, dep_type in hints.items():
            if name in overrides:
                kwargs[name] = overrides[name]
                continue
            try:
                kwargs[name] = self._resolve(
                    dep_type,
                    overrides={},
                    path=(*path, abstract),
                    requestor=requestor,
                    allow_async=False,
                )
            except BindingResolutionError as exc:
                # Re-raise with parent class in the trail.
                if isinstance(exc, CircularDependencyError):
                    raise
                # An unresolvable dep with a default falls back to it.
                if name in optional:
                    continue
                raise BindingResolutionError(
                    (*path, abstract, dep_type),
                    reason=f"required by {abstract.__qualname__}.__init__",
                ) from exc
        try:
            return abstract(**kwargs)
        except TypeError as exc:
            raise BindingResolutionError(
                (*path, abstract),
                reason=f"constructor signature mismatch: {exc}",
            ) from exc

    async def _ainstantiate(
        self,
        abstract: type[T],
        overrides: dict[str, object],
        requestor: type,
        *,
        path: tuple[type, ...] = (),
    ) -> T:
        # Async twin of _instantiate: each constructor dep goes through _aresolve
        # so a transitive async-bound dependency resolves instead of raising.
        hints = init_hints(abstract)
        optional = optional_init_params(abstract)
        kwargs: dict[str, Any] = {}
        for name, dep_type in hints.items():
            if name in overrides:
                kwargs[name] = overrides[name]
                continue
            try:
                kwargs[name] = await self._aresolve(
                    dep_type,
                    overrides={},
                    path=(*path, abstract),
                    requestor=requestor,
                )
            except BindingResolutionError as exc:
                if isinstance(exc, CircularDependencyError):
                    raise
                if name in optional:
                    continue
                raise BindingResolutionError(
                    (*path, abstract, dep_type),
                    reason=f"required by {abstract.__qualname__}.__init__",
                ) from exc
        try:
            return abstract(**kwargs)
        except TypeError as exc:
            raise BindingResolutionError(
                (*path, abstract),
                reason=f"constructor signature mismatch: {exc}",
            ) from exc

    def _invoke(
        self,
        concrete: Concrete | object,
        abstract: type,
        path: tuple[type, ...],
        *,
        overrides: dict[str, object] | None = None,
        allow_async: bool,
    ) -> Any:
        # Already-built instance passed via contextual.give(instance).
        if not callable(concrete):
            return concrete

        if is_concrete_class(concrete):
            return self._instantiate(concrete, overrides or {}, abstract, path=path)  # type: ignore[arg-type]

        # Bare callable factory.
        if is_async_callable(concrete):
            if not allow_async:
                raise AsyncBindingError(abstract)
            # Sync path can't await; caller in amake handles separately.
            msg = "Async factory invoked through sync path."
            raise RuntimeError(msg)
        return concrete(**self._factory_kwargs(concrete, overrides))

    @staticmethod
    def _factory_kwargs(
        factory: Callable[..., Any], overrides: dict[str, object] | None
    ) -> dict[str, object]:
        # Laravel passes make()'s explicit params to the binding closure. Arvel
        # factories are zero-arg by convention (they capture), so only forward
        # overrides the factory actually declares — keeps zero-arg factories intact.
        if not overrides:
            return {}
        try:
            params = inspect.signature(factory).parameters
        except TypeError, ValueError:
            return {}
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
            return dict(overrides)
        return {name: overrides[name] for name in params if name in overrides}

    def _apply_extensions(self, abstract: type, instance: Any) -> Any:
        # Walk the parent chain like _find_binding/_find_contextual — a decorator
        # registered with extend() on the root must still apply when the type is
        # resolved through a scope() child, which holds its own empty _extensions.
        container: Container | None = self
        while container is not None:
            for decorator in container._extensions.get(abstract, ()):
                instance = decorator(instance, self)
            container = container._parent
        return instance

    # ───────────────────────── Async resolution ──────────────────────────

    async def _aresolve(
        self,
        abstract: type[T],
        *,
        overrides: dict[str, object],
        path: tuple[type, ...],
        requestor: type | None,
    ) -> T:
        if not isinstance(abstract, type):  # pyright: ignore[reportUnnecessaryIsInstance]
            origin = get_origin(abstract)  # type: ignore[unreachable]
            if origin is None or not isinstance(origin, type):
                msg = f"amake() requires a type, got {type(abstract).__name__!r}."
                raise TypeError(msg)
            abstract = origin

        if abstract in path:
            raise CircularDependencyError((*path, abstract))

        if abstract in self._instances:
            return cast("T", self._instances[abstract])

        instance: Any
        if requestor is not None:
            contextual = self._find_contextual(requestor, abstract)
            if contextual is not _MISSING:
                if callable(contextual) and is_async_callable(contextual):
                    async_call: Any = contextual
                    instance = await async_call()
                    return cast("T", self._apply_extensions(abstract, instance))
                if is_concrete_class(contextual):
                    instance = await self._ainstantiate(
                        cast("type[Any]", contextual), {}, abstract, path=path
                    )
                    return cast("T", self._apply_extensions(abstract, instance))
                instance = self._invoke(contextual, abstract, path, allow_async=True)
                return cast("T", self._apply_extensions(abstract, instance))

        binding = self._find_binding(abstract)
        if binding is None:
            if inspect.isabstract(abstract):
                raise BindingResolutionError(
                    (*path, abstract),
                    reason="abstract not bound and not a concrete class",
                )
            if abstract.__init__ is object.__init__:
                raise BindingResolutionError(
                    (*path, abstract),
                    reason=(
                        f"{abstract.__qualname__} has no explicit __init__ "
                        f"and is not bound; call container.bind({abstract.__qualname__}, ...)"
                    ),
                )
            instance = await self._ainstantiate(abstract, overrides, abstract, path=path)
            return cast("T", self._apply_extensions(abstract, instance))

        # Shared scopes need a build lock: _abuild awaits, so two concurrent
        # amake() of the same singleton/scoped binding could both miss the cache
        # and build twice (doubled side effects — e.g. a second engine pool).
        if binding.scope in (Scope.SINGLETON, Scope.SCOPED):
            cache = self._singletons if binding.scope is Scope.SINGLETON else self._scope_cache
            if abstract in cache:
                return cast("T", cache[abstract])
            async with self._async_lock_for(abstract):
                if abstract in cache:  # someone built it while we waited
                    return cast("T", cache[abstract])
                instance = self._apply_extensions(
                    abstract, await self._abuild(binding, abstract, overrides, path)
                )
                cache[abstract] = instance
                return cast("T", instance)

        instance = await self._abuild(binding, abstract, overrides, path)
        return cast("T", self._apply_extensions(abstract, instance))

    async def _abuild(
        self,
        binding: _Binding,
        abstract: type,
        overrides: dict[str, object],
        path: tuple[type, ...],
    ) -> Any:
        if binding.is_async:
            async_factory: Any = binding.concrete
            return await async_factory(**self._factory_kwargs(async_factory, overrides))
        if is_concrete_class(binding.concrete):
            concrete_cls: type[Any] = binding.concrete  # type: ignore[assignment]
            return await self._ainstantiate(concrete_cls, overrides, abstract, path=path)
        sync_factory: Any = binding.concrete
        return sync_factory(**self._factory_kwargs(sync_factory, overrides))

    def _async_lock_for(self, abstract: AbstractKey) -> asyncio.Lock:
        # Locks bind to the running loop on first await, so a long-lived container
        # reused across loops (tests, separate asyncio.run calls) must get a fresh
        # lock when the loop changes. Caching is only for the cold-build window;
        # once cached, resolution never reaches here.
        loop = asyncio.get_running_loop()
        entry = self._async_locks.get(abstract)
        if entry is None or entry[0] is not loop:
            lock = asyncio.Lock()
            self._async_locks[abstract] = (loop, lock)
            return lock
        return entry[1]
