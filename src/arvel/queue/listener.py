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
    _load,  # pyright: ignore[reportPrivateUsage]
    _qualified_name,  # pyright: ignore[reportPrivateUsage]
    decode_instance,
    encode_instance,
)


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

    async def _resolve_listener(self) -> Any:
        if self.is_class:
            from arvel.kernel import app, has_application

            listener_cls = _load(self.listener_ref)
            return app().make(listener_cls) if has_application() else listener_cls()
        return await decode_instance(
            {"__class__": self.listener_ref, "__state__": self.listener_state}
        )

    async def handle(self) -> Any:
        instance = await self._resolve_listener()
        outcome = instance.handle(*self.args)
        if inspect.isawaitable(outcome):
            outcome = await outcome
        return outcome
