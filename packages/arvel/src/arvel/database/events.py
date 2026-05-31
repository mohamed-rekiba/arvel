"""Lifecycle events: Observer base class and ``Model.observe(...)`` wiring."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar, cast

from pydantic import ConfigDict

from arvel.events.event import Event as _BusEvent

if TYPE_CHECKING:
    from arvel.container import Container
    from arvel.database.model import Model

T = TypeVar("T", bound="Model")

_OBSERVERS_ATTR = "_arvel_observers"

# Task-local event mute. ContextVar (not a plain global) so suppression survives
# await boundaries and stays isolated per asyncio task under concurrency.
_suppress_events: ContextVar[bool] = ContextVar("arvel_suppress_events", default=False)


def events_suppressed() -> bool:
    """True when the current context is inside a ``without_events()`` block."""
    return _suppress_events.get()


@asynccontextmanager
async def without_events() -> AsyncGenerator[None]:
    """Mute all lifecycle events for the duration of the block. Re-entrant."""
    token = _suppress_events.set(True)
    try:
        yield
    finally:
        _suppress_events.reset(token)


class _ObserverRuntime:
    container: ClassVar[Container | None] = None


# Events fired from arvel's async persistence methods. ``trashed`` marks a soft
# delete (vs ``deleted`` which fires for both); ``force_deleted`` marks a hard
# delete; ``replicating`` fires on the fresh clone before it's returned.
_ASYNC_EVENTS = frozenset(
    {
        "created",
        "saved",
        "saving",
        "updated",
        "deleted",
        "retrieved",
        "restored",
        "trashed",
        "force_deleted",
        "replicating",
    }
)

# Before-hooks; ``False`` return aborts the pending write.
_CANCELLABLE_EVENTS = frozenset(
    {"creating", "updating", "deleting", "restoring", "force_deleting"}
)


def _get_observers(model_cls: type[Any]) -> list[Any]:
    """Return the observer list attached to ``model_cls`` (creating it if absent)."""
    observers: list[Any] | None = getattr(model_cls, _OBSERVERS_ATTR, None)
    if observers is None:
        observers = []
        setattr(model_cls, _OBSERVERS_ATTR, observers)
    return observers


async def _dispatch_observer(observer: Any, event_name: str, instance: Any) -> bool | None:
    fn = getattr(observer, event_name, None)
    if fn is None:
        return None
    result = fn(instance)
    if asyncio.iscoroutine(result):
        result = await result
    if result is False:
        return False
    return None


async def _dispatch_mapped_event(model_cls: type[Any], event_name: str, instance: Any) -> None:
    """Dispatch the ``__dispatches_events__`` event for ``event_name`` on the app bus, if any."""
    mapping: dict[str, type[Any]] | None = getattr(model_cls, "__dispatches_events__", None)
    if not mapping:
        return
    event_cls = mapping.get(event_name)
    if event_cls is None:
        return
    from arvel.facades.event import Event as EventFacade

    # No dispatcher bound (e.g. pure DB tests) — skip rather than raise.
    if EventFacade.dispatcher is None:
        return
    await EventFacade.dispatch(event_cls(model=instance))


async def fire_async(model_cls: type[Any], event_name: str, instance: Any) -> None:
    """Await all observer callbacks registered for ``event_name`` on ``model_cls``."""
    if _suppress_events.get():
        return
    for observer in _get_observers(model_cls):
        await _dispatch_observer(observer, event_name, instance)
    await _dispatch_mapped_event(model_cls, event_name, instance)


async def fire_cancellable(model_cls: type[Any], event_name: str, instance: Any) -> None:
    """Run a before-hook; abort when any observer returns ``False``."""
    if _suppress_events.get():
        return
    if event_name not in _CANCELLABLE_EVENTS:
        msg = f"fire_cancellable() only supports {_CANCELLABLE_EVENTS}, got {event_name!r}."
        raise ValueError(msg)
    from arvel.database.exceptions import OperationCancelledError

    for observer in _get_observers(model_cls):
        cancelled = await _dispatch_observer(observer, event_name, instance)
        if cancelled is False:
            raise OperationCancelledError(model_cls.__name__, event_name)
    await _dispatch_mapped_event(model_cls, event_name, instance)


class ModelEvent(_BusEvent):
    """Base for ``__dispatches_events__`` events. Carries the model instance.

    ``arbitrary_types_allowed`` lets the ORM instance ride along unvalidated.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    model: Any


class Observer(Generic[T]):
    """Base class for lifecycle observers.

    Subclasses can implement any combination of sync or async methods:
    ``creating / created / updating / updated / deleting / deleted / trashed /
    force_deleting / force_deleted / restoring / restored / replicating /
    saving / saved / retrieved``.

    ``creating``, ``updating``, ``deleting``, ``restoring``, and
    ``force_deleting`` may return ``False`` to abort the pending operation.

    ``trashed`` fires only on a soft delete, ``force_deleted`` only on a hard
    delete (``deleted`` fires for both), and ``replicating`` fires on a fresh
    clone from ``replicate()`` before it's returned.

    ``after_commit`` is called after the surrounding transaction commits. It
    receives the model instance and should be used for side-effects that must
    see committed data (e.g. refreshing a materialized view, enqueueing a job).

    Register with ``MyModel.observe(MyObserver())`` or ``MyModel.observe(MyObserver)``.
    """


def fire_after_commit(model_cls: type[Any], instance: Any) -> None:
    """Enqueue each observer's ``after_commit(instance)`` for post-transaction execution.

    Safe to call inside any lifecycle hook that runs within a DB.transaction() block.
    Does nothing for observers that don't implement ``after_commit``.
    """
    if _suppress_events.get():
        return
    from arvel.database.session import enqueue_after_commit, get_after_commit_queue

    # Short-circuit when there's no active transaction queue.
    if get_after_commit_queue() is None:
        return

    for observer in _get_observers(model_cls):
        fn: Callable[..., Awaitable[Any]] | None = getattr(observer, "after_commit", None)
        if fn is None:
            continue

        # Capture both fn and instance to avoid late-binding in the closure.
        def _make_cb(
            _fn: Callable[..., Awaitable[Any]], _inst: Any
        ) -> Callable[[], Awaitable[Any]]:
            async def _cb() -> None:
                result = _fn(_inst)
                if asyncio.iscoroutine(result):
                    await result

            return _cb

        enqueue_after_commit(_make_cb(fn, instance))


def clear_observers(model_cls: type[Any]) -> None:
    """Drop all observers registered on ``model_cls``."""
    setattr(model_cls, _OBSERVERS_ATTR, [])


def configure_observer_container(container: Container | None) -> None:
    """Bind the app container used to resolve ``Model.observe(ObserverClass)``."""
    _ObserverRuntime.container = container


def _resolve_observer(observer: type[Any] | Any) -> Any:
    if not isinstance(observer, type):
        return observer
    # No-arg observers: the container refuses classes without an explicit __init__
    # (it treats them as interface-like). Instantiate directly — same as the
    # no-container path below.
    if cast("Any", observer).__init__ is object.__init__:
        return observer()
    container = _ObserverRuntime.container
    if container is not None:
        return cast("Any", container.make(observer))
    return observer()


def bind_observer(model_cls: type[T], observer: type[Any] | Any) -> None:
    """Register ``observer`` on ``model_cls`` for lifecycle events."""
    _get_observers(model_cls).append(_resolve_observer(observer))


def observe(model_cls: type[T], observer: type[Any] | Observer[T]) -> None:
    """Bind ``observer`` to ``model_cls``'s lifecycle events."""
    bind_observer(model_cls, observer)


class _CallbackObserver:
    """One-event observer wrapping a ``callback(instance)`` (backs ``Model.on``)."""

    def __init__(self, event_name: str, callback: Callable[[Any], Any]) -> None:
        # Store under the event name so _dispatch_observer's getattr finds it.
        # Stash the callback as a plain attribute, not a bound method.
        setattr(self, event_name, callback)


def register_callback(
    model_cls: type[Any], event_name: str, callback: Callable[[Any], Any]
) -> None:
    """Register a callable for one lifecycle event (Eloquent's ``Model::created(...)``)."""
    _get_observers(model_cls).append(_CallbackObserver(event_name, callback))


__all__ = [
    "ModelEvent",
    "Observer",
    "bind_observer",
    "clear_observers",
    "configure_observer_container",
    "events_suppressed",
    "fire_after_commit",
    "fire_async",
    "fire_cancellable",
    "observe",
    "register_callback",
    "without_events",
]
