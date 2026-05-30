"""Broadcaster Protocol (FR-013-001, ADR-053)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class Broadcaster(Protocol):
    """Backend-agnostic broadcast contract.

    Every driver (log, null, redis-pubsub, pusher, in-process Reverb) implements
    this Protocol. `isinstance(driver, Broadcaster)` returns True at runtime.
    """

    async def broadcast(
        self,
        channels: Sequence[str],
        event: str,
        payload: Mapping[str, object],
        *,
        except_socket_id: str | None = None,
    ) -> None:
        """Dispatch ``event`` with ``payload`` to every channel.

        ``except_socket_id`` lets the originating Pusher connection skip its own
        echo when the driver supports it (Pusher API, Reverb internal bus).
        """
        ...


__all__ = ["Broadcaster"]
