"""arvel.database.model_events — ``HasEvents``: the full model lifecycle-event mixin
(Laravel eloquent events parity, doc 07/11). Events dispatch through the ``EventDispatcher``
**contract resolved from the container** — this module never imports ``arvel.events`` (G1
boundary).
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

# Tasks scheduled by `_fire_sync` (a sync lifecycle point firing an async event) must be kept
# referenced until done — asyncio only holds a weak reference via the loop's callback chain, and
# an unreferenced task can be garbage-collected mid-flight.
_pending_tasks: set[asyncio.Task[Any]] = set()


class HasEvents:
    """Model lifecycle events: :meth:`observe` registers an observer's hook methods;
    :meth:`_fire`/:meth:`_fire_sync` dispatch them. ``creating``/``updating``/``saving``/
    ``deleting``/``restoring`` are **cancelable** — an observer returning ``False`` aborts the
    operation and the calling method returns ``False`` (Laravel parity)."""

    #: lifecycle hooks an observer may handle, in Laravel's canonical order (doc 07/11).
    #: `creating`/`updating`/`saving`/`deleting`/`restoring` may return `False` to cancel.
    OBSERVABLE_EVENTS: ClassVar[tuple[str, ...]] = (
        "retrieved",
        "creating",
        "created",
        "updating",
        "updated",
        "saving",
        "saved",
        "deleting",
        "deleted",
        "trashed",
        "restoring",
        "restored",
        "force_deleting",
        "force_deleted",
        "replicating",
    )

    @classmethod
    def observe(cls, observer: Any) -> None:
        """Register a model observer (Laravel ``Model::observe``). For each lifecycle hook the
        observer defines a method for (any subset of :attr:`OBSERVABLE_EVENTS`), wire that method
        to this model's event so it runs when the model fires it. A cancelable hook returning
        ``False`` cancels the operation. Call from a provider's ``boot()`` (the events dispatcher
        must be bound). No-op without an app/dispatcher."""
        from arvel.kernel import app, has_application

        if not (has_application() and app().bound("events")):
            return
        instance = observer() if isinstance(observer, type) else observer
        dispatcher = app().make("events")
        for hook in cls.OBSERVABLE_EVENTS:
            method = getattr(instance, hook, None)
            if callable(method):
                dispatcher.listen(f"{cls.__name__}.{hook}", method)

    async def _fire(self, hook: str) -> Any:
        from arvel.kernel import app, has_application

        if not has_application():
            return None
        container = app()
        if not container.bound("events"):
            return None
        dispatcher = container.make("events")
        return await dispatcher.until(f"{type(self).__name__}.{hook}", self)

    def _fire_sync(self, hook: str) -> None:
        """Best-effort dispatch from a **sync** lifecycle point (``replicate()`` keeps its public
        sync signature — Laravel parity). Schedules the async dispatch on the running loop
        without blocking the caller; a no-op with no loop running (nothing would ever run the
        scheduled task anyway). Not cancelable — a sync caller can't await a verdict."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(self._fire(hook))
        _pending_tasks.add(task)
        task.add_done_callback(_pending_tasks.discard)


__all__ = ["HasEvents"]
