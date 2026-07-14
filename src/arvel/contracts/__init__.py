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

from collections.abc import Awaitable, Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, TypeVar, overload, runtime_checkable

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

    @property
    def app(
        self,
    ) -> (
        Container
    ): ...  # read-only in the contract so a concrete provider may hold any Container subtype

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
    def try_render(self, request: Any, exc: BaseException) -> Any: ...
    async def render(self, request: Any, exc: BaseException) -> Any: ...
    def render_for_console(self, output: Any, exc: BaseException) -> None: ...


@runtime_checkable
class CommandOutput(Protocol):
    """The console output surface shared by CLI commands and seeders: section/line writes plus a
    progress bar for long loops. The concrete implementation lives in ``arvel.console`` (built on
    click's ``echo``/``progressbar`` — no heavy dependency). A seeder receives one, injected by the
    ``db:seed`` runner, so ``self.with_progress_bar(...)`` renders progress without the ``database``
    layer importing the higher ``console`` layer (it depends on this contract instead)."""

    def info(self, message: str) -> None: ...
    def line(self, message: str = "") -> None: ...
    def comment(self, message: str) -> None: ...
    def warn(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...
    def new_line(self, n: int = 1) -> None: ...
    def table(self, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None: ...
    def with_progress_bar(self, iterable: Iterable[Any], *, label: str = "") -> Iterator[Any]: ...


class ModelHost:
    """Base for mixins hosted by a database model (search indexing, activity logging, …).

    Declares — for the type checker only — the model surface a mixin may call
    (``to_dict``, dirty tracking, the lifecycle-hook seam), replacing per-line ignores
    with one typed contract (DR-0037). At runtime it contributes exactly one thing: a
    cooperative ``_fire`` that forwards along the MRO, so a mixin placed *before* the
    concrete model class (the required order for its hooks to win) still reaches the
    model's event system through ``super()``.
    """

    if TYPE_CHECKING:  # provided by the concrete model the mixin is combined with
        __primary_key__: ClassVar[str]
        __table__: ClassVar[Any]
        _attributes: dict[str, Any]
        _exists: bool

        def to_dict(self) -> dict[str, Any]: ...
        def get_dirty(self) -> dict[str, Any]: ...
        def get_original(self, key: str | None = None) -> Any: ...
        async def save(self) -> bool: ...
        @classmethod
        async def all(cls) -> Any: ...

    async def _fire(self, hook: str) -> Any:
        nxt = getattr(super(), "_fire", None)
        return await nxt(hook) if nxt is not None else None


@runtime_checkable
class EventDispatcher(Protocol):
    """Event dispatch (the contract the ORM, queue, etc. resolve — they never
    import ``arvel.events`` directly)."""

    def listen(self, event: Any, listener: Callable[..., Any]) -> None: ...
    async def dispatch(self, event: Any, *payload: Any) -> list[Any]: ...
    async def until(self, event: Any, *payload: Any) -> Any: ...
    def subscribe(self, subscriber: Any) -> None: ...
    def forget(self, event: Any) -> None: ...


class HealthStatus(StrEnum):
    """The outcome of a resource health check.

    ``OK`` = healthy; ``DEGRADED`` = usable but impaired (a non-critical dependency down, a
    replica lagging); ``FAILED`` = unusable. The aggregate status is the worst of its members —
    ranked by an explicit severity map, *not* ``max`` over the enum (a ``StrEnum`` compares by
    string value, where ``"ok"`` would sort highest).
    """

    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class HealthResult:
    """A single resource's health check outcome — the value a ``Resource.check`` returns and the
    unit the startup report and ``/health`` endpoint aggregate over."""

    status: HealthStatus
    latency_ms: float = 0.0
    #: Human-readable context: ``"PING 2ms"`` on success, an error string on failure.
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is HealthStatus.OK


@runtime_checkable
class Resource(Protocol):
    """A health-checkable external dependency (database, cache, queue, …). The one contract every
    resource implements: identity + a health probe. Lifecycle (connect/disconnect) is the separate,
    optional :class:`ManagedLifecycle` — a resource with nothing to open need not implement it.

    ``critical`` decides startup policy: a failed *critical* resource aborts boot; a failed
    non-critical one degrades and boot continues. ``name`` is a stable, namespaced identifier
    (``"database"``, ``"queue:default"``) used in reports and the ``/health`` body.
    """

    name: str
    critical: bool

    async def check(self) -> HealthResult: ...


@runtime_checkable
class ManagedLifecycle(Protocol):
    """Opt-in connect/disconnect for a stateful :class:`Resource`. The manager probes for this
    (``isinstance``) and only drives lifecycle on resources that declare it — so a resource with
    no connection to open or close is never forced to stub these."""

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...


__all__ = [
    "Abstract",
    "Application",
    "CommandOutput",
    "Concrete",
    "ConfigRepository",
    "Container",
    "EventDispatcher",
    "ExceptionHandler",
    "HealthResult",
    "HealthStatus",
    "Logger",
    "ManagedLifecycle",
    "ModelHost",
    "Resource",
    "ServiceProvider",
    "Translator",
]
