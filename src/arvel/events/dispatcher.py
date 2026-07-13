"""The event dispatcher (implements ``contracts.EventDispatcher``).

Custom-by-design (DR-0002 mandates no external engine here). Supports class- and
string-named events, wildcard listeners, container-resolved class listeners,
halting (``until``), stop-propagation (a listener returning ``False``), and the
``ShouldQueue`` / ``ShouldBroadcast`` markers. ``after_commit`` events (and any work other
layers buffer via :meth:`Dispatcher.after_commit`) defer until the DB transaction commits —
``ConnectionResolver.transaction()`` opens the buffer on its outermost transaction.
"""

from __future__ import annotations

import contextlib
import fnmatch
import functools
import inspect
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

    from arvel.contracts import Container


class ShouldQueue:
    """Marker base: a listener that should run on the queue, not inline."""


class ShouldBroadcast:
    """Marker base: an event that should be broadcast to clients — **queued** by default (a small
    internal job carries the broadcast to the worker; see ``Dispatcher._broadcast``), composed
    with after-commit like a queued listener's own dispatch. Subclass :class:`ShouldBroadcastNow`
    instead for the old inline-send behavior."""


class ShouldBroadcastNow(ShouldBroadcast):
    """Marker base: broadcast **inline**, during dispatch — never queued, never deferred to a
    commit."""


class ShouldDispatchAfterCommit:
    """Marker base: an event that defers until the current DB transaction commits."""


class Dispatcher:
    def __init__(self, container: Container | None = None) -> None:
        self.container = container
        self._listeners: dict[Any, list[Any]] = {}
        self._wildcards: dict[str, list[Any]] = {}
        self._pushed: dict[Any, list[tuple[Any, ...]]] = {}  # deferred events, fired on flush()
        # Per-instance buffer of after-commit work (zero-arg async callables) while a
        # transaction is open — after-commit events and any other layer's deferred work
        # (queued-job dispatch) ride the same buffer.
        self._ac_buffer: ContextVar[list[Callable[[], Awaitable[Any]]] | None] = ContextVar(
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
                buffer.append(functools.partial(self._fire_deferred, event, payload))
                return []
        # halt=False always falls through to `_fire`'s `return results` (a list).
        result: Any = await self._fire(event, payload, halt=False)
        return cast("list[Any]", result)

    async def _fire_deferred(self, event: Any, payload: tuple[Any, ...]) -> list[Any]:
        return await self.dispatch(event, *payload)

    async def after_commit(self, callback: Callable[[], Awaitable[Any]]) -> Any:
        """Defer ``callback`` until the surrounding transaction commits; run it immediately
        when no transaction is open. The generic seam other layers use (the queue defers job
        enqueues through it), so rollback drops their work exactly like buffered events."""
        buffer = self._ac_buffer.get()
        if buffer is not None:
            buffer.append(callback)
            return None
        return await callback()

    def in_transaction(self) -> bool:
        """Whether an after-commit buffer is currently open."""
        return self._ac_buffer.get() is not None

    @staticmethod
    def _defers_to_commit(event: Any) -> bool:
        return isinstance(event, ShouldDispatchAfterCommit) or bool(
            getattr(event, "after_commit", False)
        )

    @contextlib.asynccontextmanager
    async def transaction(self) -> AsyncGenerator[Dispatcher]:
        """Buffer after-commit events; flush them on success, discard on exception.

        ``ConnectionResolver.transaction()`` wraps its outermost real transaction in this, so
        ``after_commit`` work runs only once the data is durably committed. Nested calls reuse
        the outer buffer (a savepoint release is not a commit).
        """
        if self._ac_buffer.get() is not None:
            yield self  # nested in an outer transaction — it owns the flush
            return
        buffer: list[Callable[[], Awaitable[Any]]] = []
        token = self._ac_buffer.set(buffer)
        try:
            yield self
        except BaseException:
            self._ac_buffer.reset(token)  # rolled back → drop the buffered work
            raise
        else:
            self._ac_buffer.reset(token)
            # the data already committed, so every buffered callback gets its chance — one
            # failing enqueue must not silently drop its siblings. The first failure still
            # surfaces to the caller (post-commit); none of the work is retried.
            first_failure: Exception | None = None
            for callback in buffer:
                try:
                    await callback()
                except Exception as exc:  # cancellation still propagates immediately
                    if first_failure is None:
                        first_failure = exc
            if first_failure is not None:
                raise first_failure

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
        listeners: list[tuple[Any, bool]] = [(fn, False) for fn in self._listeners.get(name, [])]
        key = name if isinstance(name, str) else getattr(name, "__name__", str(name))
        for pattern, wildcard_listeners in self._wildcards.items():
            if fnmatch.fnmatch(key, pattern):
                listeners.extend((fn, True) for fn in wildcard_listeners)
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
        """Send ``event`` to the bound ``broadcast`` manager — **queued** by default (A2-style
        seam: ``broadcast_dispatcher`` is bound by the queue provider, mirroring
        ``queue_dispatcher``'s rail for a ``ShouldQueue`` listener, since events sits below queue
        in the module DAG and must not import it). The enqueue itself rides ``after_commit``
        (this dispatcher's own deferral buffer — the generic seam other queued work uses), so a
        broadcast dispatched inside a transaction that rolls back is dropped, never sent.
        ``ShouldBroadcastNow`` skips the queue and buffer entirely: sent inline, right now. No
        ``broadcast_dispatcher`` bound (no queue provider registered) -> the same inline send,
        documented fallback (mirrors ``ShouldQueue``'s own no-queue-provider fallback)."""
        # broadcast_when(): evaluate once here at dispatch — the condition reflects dispatch-time
        # state, and a queued job can neither serialize nor meaningfully re-run the closure on the
        # worker. Once consumed, drop it so it never rides the broker (encode would choke on it).
        should = getattr(event, "should_broadcast", None)
        if callable(should) and not should():
            return
        if getattr(event, "_when", None) is not None:
            cast("Any", event)._when = None
        if isinstance(event, ShouldBroadcastNow):
            await self._broadcast_now(event)
            return
        if self.container is not None and self.container.bound("broadcast_dispatcher"):
            dispatch = self.container.make("broadcast_dispatcher")
            await self.after_commit(functools.partial(dispatch, event))
            return
        await self._broadcast_now(event)

    async def _broadcast_now(self, event: ShouldBroadcast) -> None:
        if self.container is not None and self.container.bound("broadcast"):
            await self.container.make("broadcast").broadcast(event)
