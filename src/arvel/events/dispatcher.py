"""The event dispatcher (implements ``contracts.EventDispatcher``).

Custom-by-design (DR-0002 mandates no external engine here). Supports class- and
string-named events, wildcard listeners, container-resolved class listeners,
halting (``until``), stop-propagation (a listener returning ``False``), and the
``ShouldQueue`` / ``ShouldBroadcast`` markers. ``after_commit`` events defer until
the DB transaction commits (wired when transactions land in Phase 5).

Grounded in knowledge/port/11-events.md.
"""

from __future__ import annotations

import contextlib
import fnmatch
import inspect
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from arvel.contracts import Container


class ShouldQueue:
    """Marker base: a listener that should run on the queue, not inline."""


class ShouldBroadcast:
    """Marker base: an event that should be broadcast to clients."""


class ShouldDispatchAfterCommit:
    """Marker base: an event that defers until the current DB transaction commits."""


class Dispatcher:
    def __init__(self, container: Container | None = None) -> None:
        self.container = container
        self._listeners: dict[Any, list[Any]] = {}
        self._wildcards: dict[str, list[Any]] = {}
        self._pushed: dict[Any, list[tuple[Any, ...]]] = {}  # deferred events, fired on flush()
        # Per-instance buffer of after-commit events while a transaction is open.
        self._ac_buffer: ContextVar[list[Any] | None] = ContextVar(
            f"arvel_ac_{id(self)}", default=None
        )

    def listen(self, event: Any, listener: Any) -> None:
        if isinstance(event, str) and "*" in event:
            self._wildcards.setdefault(event, []).append(listener)
        else:
            self._listeners.setdefault(event, []).append(listener)

    def forget(self, event: Any) -> None:
        self._listeners.pop(event, None)
        self._wildcards.pop(event, None)

    def has_listeners(self, event: Any) -> bool:
        """Whether any listener (direct or wildcard) is registered for ``event``
        ``Event::hasListeners``. Accepts an event class, a string name, or an instance."""
        name = event if isinstance(event, (str, type)) else type(event)
        return bool(self._gather(name))

    def push(self, event: Any, *payload: Any) -> None:
        """Register a **deferred** event to fire later via ``flush``."""
        self._pushed.setdefault(event, []).append(payload)

    async def flush(self, event: Any) -> None:
        """Dispatch all events previously ``push``-ed under ``event``."""
        for payload in self._pushed.pop(event, []):
            await self.dispatch(event, *payload)

    def forget_pushed(self) -> None:
        """Discard all pending pushed events."""
        self._pushed.clear()

    def subscribe(self, subscriber: Any) -> None:
        instance: Any = (
            cast("Any", self.container.make(subscriber))
            if isinstance(subscriber, type) and self.container is not None
            else subscriber
        )
        hook = getattr(instance, "subscribe", None)
        if callable(hook):
            hook(self)
            return
        mapping = getattr(instance, "listen", None)
        if isinstance(mapping, dict):
            for event, listeners in cast("dict[Any, list[Any]]", mapping).items():
                for listener in listeners:
                    self.listen(event, listener)

    def discover(self, listeners: Any) -> None:
        """Auto-register listener classes by their ``handle(self, event: X)`` type hint (doc 11):
        the first non-``self`` parameter's annotation is the event the listener handles."""
        import inspect
        from typing import get_type_hints

        for listener in listeners:
            handle = getattr(listener, "handle", None)
            if not callable(handle):
                continue
            try:
                params = [p for n, p in inspect.signature(handle).parameters.items() if n != "self"]
            except TypeError, ValueError:
                continue
            if not params or params[0].annotation is inspect.Parameter.empty:
                continue
            event = params[0].annotation
            if isinstance(event, str):  # `from __future__ import annotations` → resolve the string
                event = get_type_hints(handle).get(params[0].name, event)
            if isinstance(event, type):
                self.listen(event, listener)

    async def dispatch(self, event: Any, *payload: Any) -> list[Any]:
        if self._defers_to_commit(event):
            buffer = self._ac_buffer.get()
            if buffer is not None:  # a transaction is open → defer
                buffer.append((event, payload))
                return []
        # halt=False always falls through to `_fire`'s `return results` (a list).
        result: Any = await self._fire(event, payload, halt=False)
        return cast("list[Any]", result)

    @staticmethod
    def _defers_to_commit(event: Any) -> bool:
        return isinstance(event, ShouldDispatchAfterCommit) or bool(
            getattr(event, "after_commit", False)
        )

    @contextlib.asynccontextmanager
    async def transaction(self) -> AsyncGenerator[Dispatcher]:
        """Buffer after-commit events; flush them on success, discard on exception.

        The DB layer wraps a real transaction in this so ``after_commit`` events fire
        only once the data is durably committed. Nested calls reuse the outer buffer.
        """
        if self._ac_buffer.get() is not None:
            yield self  # nested in an outer transaction — it owns the flush
            return
        buffer: list[Any] = []
        token = self._ac_buffer.set(buffer)
        try:
            yield self
        except BaseException:
            self._ac_buffer.reset(token)  # rolled back → drop the buffered events
            raise
        else:
            self._ac_buffer.reset(token)
            for event, payload in buffer:
                await self.dispatch(event, *payload)

    async def until(self, event: Any, *payload: Any) -> Any:
        return await self._fire(event, payload, halt=True)

    async def _fire(self, event: Any, payload: tuple[Any, ...], *, halt: bool) -> Any:
        if isinstance(event, ShouldBroadcast):
            await self._broadcast(event)
        name, args = self._parse(event, payload)
        key = name if isinstance(name, str) else getattr(name, "__name__", str(name))
        results: list[Any] = []
        for listener, is_wildcard in self._gather(name):
            # a wildcard listener handles many events, so it receives the event name first
            call_args = (key, *args) if is_wildcard else args
            if await self._queue_if_needed(listener, call_args):
                continue
            handler = self._resolve(listener)
            outcome = handler(*call_args)
            if inspect.isawaitable(outcome):
                outcome = await outcome
            if halt and outcome is not None:
                return outcome
            if outcome is False:
                break
            results.append(outcome)
        return results

    def _parse(self, event: Any, payload: tuple[Any, ...]) -> tuple[Any, tuple[Any, ...]]:
        if isinstance(event, str):
            return event, payload
        event_type: Any = cast("Any", type(event))
        return event_type, (event, *payload)

    def _gather(self, name: Any) -> list[tuple[Any, bool]]:
        listeners: list[tuple[Any, bool]] = [(l, False) for l in self._listeners.get(name, [])]
        key = name if isinstance(name, str) else getattr(name, "__name__", str(name))
        for pattern, wildcard_listeners in self._wildcards.items():
            if fnmatch.fnmatch(key, pattern):
                listeners.extend((l, True) for l in wildcard_listeners)
        return listeners

    def _resolve(self, listener: Any) -> Any:
        if not isinstance(listener, type):
            return listener
        instance = self._instantiate(listener)
        handle = getattr(instance, "handle", None)
        return handle if callable(handle) else instance

    def _instantiate(self, listener_cls: type[Any]) -> Any:
        if self.container is not None:
            return self.container.make(listener_cls)
        return listener_cls()

    async def _queue_if_needed(self, listener: Any, args: tuple[Any, ...]) -> bool:
        """Enqueue a ``ShouldQueue`` listener via the container-bound ``queue_dispatcher`` contract
        (A2) — events sits *below* queue in the module DAG and must not import it; the queue
        provider binds this seam instead (see ``queue.provider.QueueServiceProvider``). No
        ``queue_dispatcher`` bound (no queue provider registered) -> run inline (documented
        fallback), same as a non-queued listener."""
        is_queued = (
            isinstance(listener, type) and issubclass(listener, ShouldQueue)
        ) or isinstance(listener, ShouldQueue)
        if is_queued and self.container is not None and self.container.bound("queue_dispatcher"):
            dispatch = self.container.make("queue_dispatcher")
            await dispatch(listener, args)
            return True
        return False

    async def _broadcast(self, event: ShouldBroadcast) -> None:
        if self.container is not None and self.container.bound("broadcast"):
            await self.container.make("broadcast").broadcast(event)
