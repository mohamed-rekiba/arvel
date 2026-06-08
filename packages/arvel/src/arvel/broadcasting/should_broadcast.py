"""ShouldBroadcast mixin."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast


class ShouldBroadcast:
    """Marker mixin. Events that mix this in are routed through ``Broadcast.send``
    by ``EventDispatcher`` after sync listeners finish.

    Subclasses MUST override ``broadcast_on``. They MAY override ``broadcast_as``
    (default: class name) and ``broadcast_with`` (default: ``model_dump()`` for
    Pydantic BaseModel events, otherwise an empty dict).
    """

    def broadcast_on(self) -> Sequence[str]:
        raise NotImplementedError(
            f"{type(self).__name__} must override broadcast_on() to return the "
            f"list of channel names this event broadcasts to.",
        )

    def broadcast_as(self) -> str:
        return type(self).__name__

    def broadcast_with(self) -> Mapping[str, object]:
        dump = getattr(self, "model_dump", None)
        if callable(dump):
            # mode="json" so datetime/UUID/Decimal land as JSON-safe values — the
            # drivers json.dumps the payload, and python-mode dumps would blow up.
            return _as_payload_mapping(dump(mode="json"))
        return {}


def _as_payload_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}
    typed = cast("Mapping[Any, Any]", value)  # type: ignore[redundant-cast]
    return {str(k): v for k, v in typed.items()}


__all__ = ["ShouldBroadcast"]
