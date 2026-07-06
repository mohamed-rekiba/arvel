"""The service container — bind abstractions to concretes and resolve them.

The innermost module: imports only ``arvel.contracts`` + stdlib. Autowiring uses
``inspect`` + ``typing.get_type_hints`` (not PHP-style reflection). Implements the
``arvel.contracts.Container`` protocol.

Grounded in knowledge/port/02-container.md.
"""

from __future__ import annotations

import contextvars
import functools
import inspect
import typing
from collections.abc import Callable, Sequence
from typing import Any, TypedDict, TypeVar, cast, overload

T = TypeVar("T")

_PRIMITIVES = (int, float, str, bool, bytes, complex)

#: Builtin collection types that must never be autowired (make(list) → [] was a silent footgun).
_UNBUILDABLE_BUILTINS = (list, dict, set, frozenset, tuple)

_UNSET: Any = object()  # "no value resolved yet" sentinel in dependency resolution

#: Per-scope instance cache (e.g. per-request). ``None`` when no scope is active.
_scope: contextvars.ContextVar[dict[Any, Any] | None] = contextvars.ContextVar(
    "arvel_container_scope", default=None
)


class _ScopeGuard:
    """A resolution scope — scoped bindings share one instance within it. Usable three ways:

    - ``with container.scope(): ...`` or ``async with container.scope(): ...``
    - ``@container.scope()`` on a **sync or async** function — each call runs in a fresh scope.

    (A plain ``@contextmanager`` only decorates *sync* functions correctly; this also handles
    coroutines, opening the scope for the whole ``await`` rather than closing it first.)
    """

    __slots__ = ("_token",)

    def __init__(self) -> None:
        self._token: Any = None

    def __enter__(self) -> None:
        self._token = _scope.set({})

    def __exit__(self, *exc: object) -> None:
        _scope.reset(self._token)

    async def __aenter__(self) -> None:
        self._token = _scope.set({})

    async def __aexit__(self, *exc: object) -> None:
        _scope.reset(self._token)

    def __call__(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def awrapper(*args: Any, **kwargs: Any) -> Any:
                token = _scope.set({})
                try:
                    return await fn(*args, **kwargs)
                finally:
                    _scope.reset(token)

            return awrapper

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            token = _scope.set({})
            try:
                return fn(*args, **kwargs)
            finally:
                _scope.reset(token)

        return wrapper


class BindingResolutionError(Exception):
    """A binding could not be resolved (unbound, not instantiable, primitive)."""


class CircularDependencyError(BindingResolutionError):
    """A dependency cycle was detected while autowiring."""


@functools.lru_cache(maxsize=1024)
def _init_signature(concrete: Any) -> tuple[inspect.Signature | None, dict[str, Any]]:
    """Memoize a class's ``__init__`` signature + resolved type hints — pure per class and
    hot on every autowired ``make``. ``get_type_hints`` is the expensive part. Returns
    ``(None, {})`` when the signature can't be introspected (→ no-arg construction). Bounded
    cache keyed on the class object; the set of injectable classes is finite."""
    try:
        sig = inspect.signature(concrete.__init__)
    except ValueError, TypeError:
        return None, {}
    try:
        hints = typing.get_type_hints(concrete.__init__)
    except Exception:
        # an unresolvable forward ref raises NameError — fall back to raw annotations rather than fail
        hints = {}
    return sig, hints


class _Binding(TypedDict):
    concrete: Any
    shared: bool
    scoped: bool


class ContextualBindingBuilder:
    """Fluent builder for ``container.when(A).needs(B).give(C)``."""

    def __init__(self, container: Container, concrete: Any) -> None:
        self._container = container
        self._concrete = concrete
        self._needs: Any = None

    def needs(self, abstract: Any) -> ContextualBindingBuilder:
        self._needs = abstract
        return self

    def give(self, implementation: Any) -> None:
        self._container._add_contextual(  # pyright: ignore[reportPrivateUsage]
            self._concrete, self._needs, implementation
        )


class Container:
    """A service container with autowiring, singletons, scopes, contextual
    bindings, tags, extenders, and resolving hooks."""

    def __init__(self) -> None:
        self._bindings: dict[Any, _Binding] = {}
        self._instances: dict[Any, Any] = {}
        self._aliases: dict[Any, Any] = {}
        self._extenders: dict[Any, list[Callable[[Any, Container], Any]]] = {}
        self._contextual: dict[Any, dict[Any, Any]] = {}
        self._tags: dict[str, list[Any]] = {}
        self._resolving_cbs: dict[Any, list[Callable[[Any, Container], None]]] = {}
        self._after_resolving_cbs: dict[Any, list[Callable[[Any, Container], None]]] = {}
        self._method_bindings: dict[tuple[type, str], Callable[[Any, Container], Any]] = {}
        self._build_stack: list[Any] = []
        self._with: list[dict[str, Any]] = []

    # --- binding -----------------------------------------------------------
    def bind(
        self,
        abstract: Any,
        concrete: Any = None,
        *,
        shared: bool = False,
        scoped: bool = False,
    ) -> None:
        self._bindings[self._alias_of(abstract)] = {
            "concrete": abstract if concrete is None else concrete,
            "shared": shared,
            "scoped": scoped,
        }

    def singleton(self, abstract: Any, concrete: Any = None) -> None:
        self.bind(abstract, concrete, shared=True)

    def scoped(self, abstract: Any, concrete: Any = None) -> None:
        self.bind(abstract, concrete, scoped=True)

    def instance(self, abstract: Any, obj: Any) -> Any:
        self._instances[self._alias_of(abstract)] = obj
        return obj

    def alias(self, alias: str, abstract: Any) -> None:
        self._aliases[alias] = abstract

    def extend(self, abstract: Any, closure: Callable[[Any, Container], Any]) -> None:
        """Wrap the resolution of ``abstract`` with ``closure(instance, container)``.
        If ``abstract`` is already resolved as a shared instance, the closure is applied to
        that instance *immediately* (it will never rebuild), mirroring ``extend``;
        otherwise the closure runs at the next build."""
        key = self._alias_of(abstract)
        if key in self._instances:
            self._instances[key] = closure(self._instances[key], self)
        else:
            self._extenders.setdefault(key, []).append(closure)

    def tag(self, abstracts: Sequence[Any], tag: str) -> None:
        self._tags.setdefault(tag, []).extend(abstracts)

    def tagged(self, tag: str) -> list[Any]:
        return [self.make(a) for a in self._tags.get(tag, [])]

    def resolving(self, abstract: Any, callback: Callable[[Any, Container], None]) -> None:
        self._resolving_cbs.setdefault(self._alias_of(abstract), []).append(callback)

    def after_resolving(self, abstract: Any, callback: Callable[[Any, Container], None]) -> None:
        """Register ``callback(instance, container)`` to fire on each resolve of ``abstract``,
        *after* its ``resolving`` callbacks."""
        self._after_resolving_cbs.setdefault(self._alias_of(abstract), []).append(callback)

    def bind_method(self, target: Sequence[Any], callback: Callable[[Any, Container], Any]) -> None:
        """Override how a method is resolved by ``call``. ``target`` is
        ``[Cls, "method"]``; ``call((instance, "method"))`` then invokes ``callback(instance,
        container)`` instead of the original method."""
        cls, method = target[0], target[1]
        self._method_bindings[(cls, method)] = callback

    def when(self, concrete: Any) -> ContextualBindingBuilder:
        return ContextualBindingBuilder(self, concrete)

    def _add_contextual(self, concrete: Any, needs: Any, implementation: Any) -> None:
        self._contextual.setdefault(concrete, {})[needs] = implementation

    def bound(self, abstract: Any) -> bool:
        a = self._alias_of(abstract)
        return a in self._bindings or a in self._instances

    def forget(self, abstract: Any) -> None:
        """Drop ``abstract``'s cached shared instance + any current-scope instance so the next
        ``make`` rebuilds it. The *binding* is kept."""
        key = self._alias_of(abstract)
        self._instances.pop(key, None)
        scope = _scope.get()
        if scope is not None:
            scope.pop(key, None)

    def flush(self) -> None:
        """Clear all bindings, shared instances, aliases, tags, and extenders.
        Resolution hooks/contextual bindings are kept; mostly used to reset a container in tests."""
        self._bindings.clear()
        self._instances.clear()
        self._extenders.clear()
        self._aliases.clear()
        self._tags.clear()

    # --- resolution --------------------------------------------------------
    @overload
    def make(self, abstract: type[T], /, **params: Any) -> T: ...
    @overload
    def make(self, abstract: str, /, **params: Any) -> Any: ...
    def make(self, abstract: Any, /, **params: Any) -> Any:
        return self._resolve(abstract, params)

    def __getitem__(self, abstract: Any) -> Any:
        return self.make(abstract)

    def __contains__(self, abstract: Any) -> bool:
        return self.bound(abstract)

    def _alias_of(self, abstract: Any) -> Any:
        seen: set[Any] = set()
        while isinstance(abstract, str) and abstract in self._aliases and abstract not in seen:
            seen.add(abstract)
            abstract = self._aliases[abstract]
        return abstract

    def _contextual_concrete(self, abstract: Any) -> Any:
        if self._build_stack:
            ctx = self._contextual.get(self._build_stack[-1])
            if ctx and abstract in ctx:
                return ctx[abstract]
        return None

    def _resolve(self, abstract: Any, params: dict[str, Any] | None = None) -> Any:
        params = params or {}
        abstract = self._alias_of(abstract)
        ctx = self._contextual_concrete(abstract)
        needs_ctx = bool(params) or ctx is not None
        binding = self._bindings.get(abstract)

        if binding is not None and binding["scoped"]:
            return self._resolve_scoped(abstract, binding["concrete"])
        if abstract in self._instances and not needs_ctx:
            return self._instances[abstract]

        self._with.append(params)
        try:
            if ctx is not None:
                obj = self._from_contextual(ctx)
            else:
                concrete = binding["concrete"] if binding is not None else abstract
                obj = (
                    self._build(concrete)
                    if self._buildable(concrete, abstract)
                    else self._resolve(concrete)
                )
            for ext in self._extenders.get(abstract, []):
                obj = ext(obj, self)
            if binding is not None and binding["shared"] and not needs_ctx:
                self._instances[abstract] = obj
            self._fire_resolution_callbacks(abstract, obj)
            return obj
        finally:
            self._with.pop()

    def _buildable(self, concrete: Any, abstract: Any) -> bool:
        return concrete is abstract or (callable(concrete) and not isinstance(concrete, str))

    def _from_contextual(self, implementation: Any) -> Any:
        if inspect.isclass(implementation):
            return self.make(implementation)
        if callable(implementation):
            return self._call_factory(implementation)
        return implementation  # a literal value

    def _build(self, concrete: Any) -> Any:
        if callable(concrete) and not inspect.isclass(concrete):
            return self._call_factory(concrete)
        if not inspect.isclass(concrete):
            raise BindingResolutionError(f"Target [{concrete!r}] is not instantiable.")
        if concrete in _UNBUILDABLE_BUILTINS:
            # a bare builtin collection is never a service; require an explicit bind()/instance()
            raise BindingResolutionError(
                f"Cannot autowire the builtin {concrete.__name__!r} — bind it explicitly "
                f"(container.instance(...) / container.bind(...))."
            )
        if concrete in self._build_stack:
            raise CircularDependencyError(
                f"Circular dependency: {concrete!r} (stack: {self._build_stack!r})"
            )
        if inspect.isabstract(concrete):
            raise BindingResolutionError(f"Target [{concrete!r}] is abstract; bind a concrete.")
        if getattr(concrete, "_is_protocol", False):
            # a Protocol has no runtime constructor; isabstract() misses it (its methods rarely
            # carry @abstractmethod). Raise the resolution error so an optional param still falls
            # back to its default rather than leaking TypeError("Protocols cannot be instantiated").
            raise BindingResolutionError(
                f"Target [{concrete!r}] is a Protocol; bind a concrete implementation."
            )

        self._build_stack.append(concrete)
        try:
            sig, hints = _init_signature(cast("Any", concrete))
            if sig is None:  # __init__ not introspectable → no-arg construction
                return concrete()
            args, kwargs = self._resolve_dependencies(sig, hints, concrete)
        finally:
            self._build_stack.pop()
        return concrete(*args, **kwargs)

    def _call_factory(self, fn: Callable[..., Any]) -> Any:
        override = self._with[-1] if self._with else {}
        nargs = self._positional_arity(fn)
        return fn(*(self, override)[:nargs])

    @staticmethod
    def _positional_arity(fn: Callable[..., Any]) -> int:
        try:
            params = inspect.signature(fn).parameters.values()
        except ValueError, TypeError:
            return 0
        kinds = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        return min(2, sum(1 for p in params if p.kind in kinds))

    def _resolve_dependencies(
        self, sig: inspect.Signature, hints: dict[str, Any], owner: Any
    ) -> tuple[list[Any], dict[str, Any]]:
        """Resolve ctor params into ``(positional_args, keyword_args)``. Keyword-only params are
        kept as kwargs so they're never passed positionally (M2). A non-buildable annotation
        (``typing.Any``, a generic, an unresolvable ref) falls back to the param's default/``None``
        when it has one, else raises a clear ``BindingResolutionError`` rather than leaking a raw
        ``TypeError``/``NameError`` (M1/C3)."""
        override = self._with[-1] if self._with else {}
        args: list[Any] = []
        kwargs: dict[str, Any] = {}
        empty = inspect.Parameter.empty
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            if name in override:
                value = override[name]
            else:
                annotation = hints.get(name, param.annotation)
                inner, nullable = self._unwrap_optional(annotation)
                has_default = param.default is not empty
                value = _UNSET
                if self._is_injectable(inner):
                    try:
                        value = self.make(inner)
                    except CircularDependencyError:
                        raise  # a dependency cycle is always fatal — never silently fall back
                    except BindingResolutionError:
                        # inner is unbuildable (unbound/abstract) → fall back; a real error from a
                        # buildable dep's __init__ still propagates, never masked as "unresolvable"
                        if not (has_default or nullable):
                            raise
                if value is _UNSET:
                    if has_default:
                        value = param.default
                    elif nullable:
                        value = None
                    else:
                        raise BindingResolutionError(
                            f"Unresolvable dependency [{name}: {annotation!r}] building {owner!r}"
                        )
            if param.kind == param.KEYWORD_ONLY:
                kwargs[name] = value
            else:
                args.append(value)
        return args, kwargs

    def _resolve_scoped(self, abstract: Any, concrete: Any) -> Any:
        def build() -> Any:
            obj = (
                self._build(concrete)
                if self._buildable(concrete, abstract)
                else self._resolve(concrete)
            )
            for ext in self._extenders.get(abstract, []):  # extend() also decorates scoped bindings
                obj = ext(obj, self)
            self._fire_resolution_callbacks(abstract, obj)
            return obj

        scope = _scope.get()
        if scope is None:
            return build()
        if abstract not in scope:
            scope[abstract] = build()
        return scope[abstract]

    def scope(self) -> _ScopeGuard:
        """Open a resolution scope (scoped bindings share one instance within it). Use as a
        context manager — ``with``/``async with`` — or as a decorator ``@container.scope()`` on a
        sync or async function (each call then runs in its own fresh scope)."""
        return _ScopeGuard()

    def _fire_resolution_callbacks(self, abstract: Any, obj: Any) -> None:
        for cb in self._resolving_cbs.get(abstract, []):
            cb(obj, self)
        for cb in self._after_resolving_cbs.get(abstract, []):
            cb(obj, self)

    # --- callable injection (async-aware) ----------------------------------
    def call(self, target: Callable[..., Any] | tuple[object, str], /, **params: Any) -> Any:
        if isinstance(target, tuple):
            # cast for pyright (it keeps an Unknown otherwise); mypy already narrows.
            instance, method = cast("tuple[object, str]", target)
            bound = self._method_bindings.get((type(instance), method))
            if bound is not None:  # custom method resolution (bind_method)
                return bound(instance, self)
            func: Callable[..., Any] = getattr(instance, method)
        else:
            func = target
        try:
            sig = inspect.signature(func)
        except ValueError, TypeError:
            return func()
        try:
            hints = typing.get_type_hints(func)
        except Exception:
            hints = {}  # unresolvable hints → inject only what we can introspect
        kwargs: dict[str, Any] = {}
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            if name in params:
                kwargs[name] = params[name]
                continue
            annotation = hints.get(name, param.annotation)
            if self._is_injectable(annotation):
                kwargs[name] = self.make(annotation)
            elif param.default is not inspect.Parameter.empty:
                kwargs[name] = param.default
        return func(**kwargs)  # a coroutine is returned untouched for async targets

    # --- helpers -----------------------------------------------------------
    @staticmethod
    def _is_primitive(annotation: Any) -> bool:
        return annotation in _PRIMITIVES

    @staticmethod
    def _is_injectable(annotation: Any) -> bool:
        """Whether the container should try to autowire ``annotation``: only a concrete, non-primitive
        **class**. ``Any``, ``None``, primitives, generics (``list[str]``), string/forward-ref
        annotations, and ``TypeVar``s are non-injectable — the param's default/``None`` is used
        instead. Restricting to real classes means ``make`` is attempted only on buildable targets,
        so a genuine error from a dependency's constructor isn't mistaken for an unresolvable binding.
        """
        if annotation is inspect.Parameter.empty or annotation is None or annotation is Any:
            return False
        if annotation in _PRIMITIVES:
            return False
        return inspect.isclass(annotation)

    @staticmethod
    def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
        """Return (resolvable_type, is_nullable). ``Optional[X]`` → ``(X, True)``;
        a non-optional annotation → ``(annotation, False)``; an ambiguous union →
        ``(None, True)``."""
        args = typing.get_args(annotation)
        if args and type(None) in args:
            non_none = [a for a in args if a is not type(None)]
            return (non_none[0] if len(non_none) == 1 else None, True)
        return (annotation, False)
