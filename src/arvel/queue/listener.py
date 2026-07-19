"""``CallQueuedListener`` — the worker job that runs a queued event listener.

A2: ``events`` sits *below* ``queue`` in the module DAG and must not import it, so it can't push a
job directly. Instead the queue provider binds a ``queue_dispatcher`` callable into the container;
``events.Dispatcher._queue_if_needed`` calls that contract, which builds and pushes this job. Kept
in its own module (like ``queue/jobs.py``/``queue/failed.py``) so `import arvel.queue` stays light.
"""

from __future__ import annotations

import inspect
from typing import Any

from arvel.queue import (
    Job,
    _qualified_name,  # pyright: ignore[reportPrivateUsage]
    encode_instance,
)
from arvel.queue.serialization import _rehydrate  # pyright: ignore[reportPrivateUsage]


class CallQueuedListener(Job):
    """Runs a ``ShouldQueue`` event listener on the worker.

    A listener registered as a **class** (the common case — ``d.listen(Event, MyListener)``) is
    carried as a qualified class ref and container-resolved fresh in the worker (mirrors inline
    dispatch's own listener resolution). An already-constructed listener **instance** is carried
    as an encoded ``{class, state}`` view (``encode_instance``/``decode_instance`` — the same rail
    a queued Mailable/Notification uses).
    """

    def __init__(
        self,
        listener_ref: str,
        *,
        is_class: bool,
        listener_state: dict[str, Any] | None,
        args: tuple[Any, ...],
    ) -> None:
        self.listener_ref = listener_ref
        self.is_class = is_class
        self.listener_state = listener_state
        self.args = args

    @classmethod
    def for_listener(cls, listener: Any, args: tuple[Any, ...]) -> CallQueuedListener:
        if isinstance(listener, type):
            return cls(_qualified_name(listener), is_class=True, listener_state=None, args=args)
        encoded = encode_instance(listener)
        return cls(
            str(encoded["__class__"]),
            is_class=False,
            listener_state=encoded["__state__"],
            args=args,
        )

    def _registered_listener(self) -> Any:
        """Resolve `listener_ref` against the queued-listener registry — a lookup, never an import.

        This job's own class passes the deserializer's allowlist legitimately, but its state is
        attacker-settable on a tampered payload, and `listener_ref` used to be handed straight to
        `_load`. That reopened the exact hole the allowlist closed: import an arbitrary name, then
        call `handle(*args)` on it with attacker-controlled arguments (GH-301).

        Only `ShouldQueue` subclasses are ever queued, and a listener must be imported before it
        can be registered with the dispatcher, so any reference that legitimately reaches a worker
        is already in the registry.
        """
        from arvel.events.dispatcher import _QUEUED_LISTENERS  # pyright: ignore[reportPrivateUsage]

        listener_cls = _QUEUED_LISTENERS.get(self.listener_ref)
        if listener_cls is None:
            raise ValueError(
                f"refusing to load unregistered listener {self.listener_ref!r} from a queue "
                "payload — a queued listener must subclass arvel.events.ShouldQueue"
            )
        return listener_cls

    async def _resolve_listener(self) -> Any:
        listener_cls = self._registered_listener()
        if self.is_class:
            from arvel.kernel import app, has_application

            return app().make(listener_cls) if has_application() else listener_cls()
        instance = listener_cls.__new__(listener_cls)
        for key, value in (self.listener_state or {}).items():
            setattr(instance, key, await _rehydrate(value))
        return instance

    async def handle(self) -> Any:
        instance = await self._resolve_listener()
        outcome = instance.handle(*self.args)
        if inspect.isawaitable(outcome):
            outcome = await outcome
        return outcome

    async def failed(self, exc: BaseException) -> None:
        """On retry exhaustion, delegate to the wrapped listener's own ``failed(exc)`` (if it
        defines one) exactly once — mirrors a job's own ``failed()`` hook, for a queued listener.
        Resolving the listener again, or the hook itself, raising is logged and swallowed: one
        broken failure-hook must never crash the worker (``run_job_with_retries`` awaits this
        directly from ``_give_up``, unguarded)."""
        from arvel.kernel.logging import LogManager

        try:
            instance = await self._resolve_listener()
        except Exception:
            LogManager().channel("queue").warning(
                "queued_listener_failed_hook_resolve_failed", exc_info=True
            )
            return
        hook = getattr(instance, "failed", None)
        if not callable(hook):
            return
        try:
            outcome = hook(exc)
            if inspect.isawaitable(outcome):
                await outcome
        except Exception:
            LogManager().channel("queue").error("queued_listener_failed_hook_raised", exc_info=True)
