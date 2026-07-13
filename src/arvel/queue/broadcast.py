"""``CallQueuedBroadcast`` — the worker job that delivers a queued ``ShouldBroadcast`` event.

Mirrors ``queue/listener.py``'s ``CallQueuedListener``: the event dispatcher (below ``queue`` in
the module DAG, see 5.7/A2) can't push a job directly, so the queue provider binds a
``broadcast_dispatcher`` contract that builds and pushes this one. Kept in its own module (like
``queue/listener.py``/``queue/failed.py``) so ``import arvel.queue`` stays light.
"""

from __future__ import annotations

from typing import Any

from arvel.queue import Job, decode_instance, encode_instance


class CallQueuedBroadcast(Job):
    """Runs a queued ``ShouldBroadcast`` event's delivery on the worker — the event is carried as
    an encoded ``{class, state}`` view (``encode_instance``/``decode_instance``, the same rail a
    queued Mailable/Notification/listener instance uses) and re-sent through the bound
    ``broadcast`` manager."""

    def __init__(self, event_ref: str, event_state: dict[str, Any]) -> None:
        self.event_ref = event_ref
        self.event_state = event_state

    @classmethod
    def for_event(cls, event: Any) -> CallQueuedBroadcast:
        encoded = encode_instance(event)
        return cls(str(encoded["__class__"]), encoded["__state__"])

    async def handle(self) -> Any:
        from arvel.kernel import app

        event = await decode_instance({"__class__": self.event_ref, "__state__": self.event_state})
        await app().make("broadcast").broadcast(event)
