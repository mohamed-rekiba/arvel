"""The queued-indexing seam's provided listener.

Register it against ``ModelIndexRequested`` so a ``search.queue``-enabled save/delete still
reaches the engine — just via the events dispatcher instead of an inline call in ``Searchable``.
``SearchServiceProvider.boot()`` registers it automatically when ``search.queue`` is on and an
events dispatcher is bound::

    app.make("events").listen(ModelIndexRequested, handle_index_request)

This runs the write as soon as the event is dispatched (proving the event/listener seam end to
end); moving that off the request path onto a real background worker (``ShouldQueue`` + a queue
broker) is QUEUE-RELIABILITY's story, not this one — and this module still never imports
``arvel.queue`` (G1 boundary).
"""

from __future__ import annotations

from typing import Any

from arvel.search import ModelIndexRequested


async def handle_index_request(event: ModelIndexRequested) -> None:
    """Perform the write a queued ``Searchable`` save/delete deferred: index ``event.record``,
    or delete ``event.key`` when ``event.record`` is ``None``. A no-op without a bound engine."""
    from arvel.kernel import app, has_application

    if not (has_application() and app().bound("search")):
        return
    engine: Any = app("search")
    index = event.model_class.searchable_as()
    if event.record is None:
        await engine.delete(index, event.key)
    else:
        await engine.index(index, event.key, event.record)


__all__ = ["handle_index_request"]
