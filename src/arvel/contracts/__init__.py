"""arvel.contracts — public, semver-stable interfaces (Protocols).

The plugin boundary: the surface ecosystem packages target, and the only thing
capability modules share with one another (cross-capability behavior is reached
through a contract resolved from the container — never by importing a sibling's
internals). This module imports **only** ``typing``/stdlib, so it is safe for any
module (including the kernel) to depend on and never drags in a heavy library.

T0.2 defines the **foundation** Protocols (container, application, config,
providers) plus the named cross-cutting ones (``Logger``, ``Translator``,
``ExceptionHandler``, ``EventDispatcher``). Capability Protocols (``Kernel``,
``Router``, ``Cache``, ``Queue``, ``Filesystem``, …) are added alongside their
modules in later phases, exactly as the import-linter layered DAG grows.

Grounded in knowledge/port/02-container.md and 03-application-providers-bootstrap.md.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Protocol, TypeVar, overload, runtime_checkable

T = TypeVar("T")

#: An abstract a binding can be keyed by: a type (autowired) or a string name.
Abstract = type[Any] | str
#: A concrete: a class, a factory callable ``(app, params) -> obj``, or ``None``.
Concrete = type[Any] | Callable[..., Any] | None


@runtime_checkable
class Container(Protocol):
    """The service container: bind abstractions to concretes and resolve them."""

    def bind(
        self,
        abstract: Abstract,
        concrete: Concrete = None,
        *,
        shared: bool = False,
        scoped: bool = False,
    ) -> None: ...
    def singleton(self, abstract: Abstract, concrete: Concrete = None) -> None: ...
    def scoped(self, abstract: Abstract, concrete: Concrete = None) -> None: ...
    def instance(self, abstract: Abstract, obj: T) -> T: ...
    def alias(self, alias: str, abstract: Abstract) -> None: ...
    def extend(self, abstract: Abstract, closure: Callable[[Any, Container], Any]) -> None: ...

    @overload
    def make(self, abstract: type[T], /, **params: Any) -> T: ...
    @overload
    def make(self, abstract: str, /, **params: Any) -> Any: ...

    def call(self, target: Callable[..., Any] | tuple[object, str], /, **params: Any) -> Any: ...
    def bound(self, abstract: Abstract) -> bool: ...
    def tag(self, abstracts: Sequence[Abstract], tag: str) -> None: ...
    def tagged(self, tag: str) -> Sequence[Any]: ...
    def resolving(self, abstract: Abstract, callback: Callable[[Any, Container], None]) -> None: ...


@runtime_checkable
class ServiceProvider(Protocol):
    """Registers (and boots) services. ``register`` is sync (bindings only);
    ``boot`` may be sync or async. The base class + integration verbs live in
    ``arvel.kernel``; this is the structural contract."""

    app: Container

    def register(self) -> None: ...
    def boot(self) -> Awaitable[None] | None: ...
    def provides(self) -> Sequence[Abstract]: ...


@runtime_checkable
class Application(Container, Protocol):
    """The application: a container that registers providers and boots them,
    integrated with the ASGI lifespan."""

    base_path: str

    def register(self, provider: ServiceProvider) -> ServiceProvider: ...
    async def boot(self) -> None: ...
    def terminating(self, callback: Callable[[], Any]) -> None: ...

    @overload
    def config(self) -> ConfigRepository: ...
    @overload
    def config(self, key: str, default: Any = ...) -> Any: ...


@runtime_checkable
class ConfigRepository(Protocol):
    """Dotted-key configuration access (``config('app.name')``)."""

    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...
    def has(self, key: str) -> bool: ...
    def all(self) -> Mapping[str, Any]: ...


@runtime_checkable
class Logger(Protocol):
    """Structured logger (structlog-backed). ``bind`` adds context; ``channel``
    selects a named sink."""

    def debug(self, event: str, **kw: Any) -> None: ...
    def info(self, event: str, **kw: Any) -> None: ...
    def warning(self, event: str, **kw: Any) -> None: ...
    def error(self, event: str, **kw: Any) -> None: ...
    def critical(self, event: str, **kw: Any) -> None: ...
    def bind(self, **kw: Any) -> Logger: ...
    def channel(self, name: str) -> Logger: ...


@runtime_checkable
class Translator(Protocol):
    """Localization lookup with placeholder replacement + pluralization (Babel)."""

    def get(
        self, key: str, replace: Mapping[str, Any] | None = None, locale: str | None = None
    ) -> str: ...
    def choice(
        self,
        key: str,
        number: int,
        replace: Mapping[str, Any] | None = None,
        locale: str | None = None,
    ) -> str: ...
    def get_locale(self) -> str: ...
    def set_locale(self, locale: str) -> None: ...


@runtime_checkable
class ExceptionHandler(Protocol):
    """The single global exception handler (HTTP + console + queue + uncaught)."""

    def report(self, exc: BaseException) -> None: ...
    def should_report(self, exc: BaseException) -> bool: ...
    def try_render(self, request: Any, exc: BaseException) -> Any | None: ...
    async def render(self, request: Any, exc: BaseException) -> Any: ...
    def render_for_console(self, output: Any, exc: BaseException) -> None: ...


@runtime_checkable
class EventDispatcher(Protocol):
    """Event dispatch (the contract the ORM, queue, etc. resolve — they never
    import ``arvel.events`` directly)."""

    def listen(self, event: Any, listener: Callable[..., Any]) -> None: ...
    async def dispatch(self, event: Any, *payload: Any) -> list[Any]: ...
    async def until(self, event: Any, *payload: Any) -> Any: ...
    def subscribe(self, subscriber: Any) -> None: ...
    def forget(self, event: Any) -> None: ...


__all__ = [
    "Abstract",
    "Application",
    "Concrete",
    "ConfigRepository",
    "Container",
    "EventDispatcher",
    "ExceptionHandler",
    "Logger",
    "ServiceProvider",
    "Translator",
]
