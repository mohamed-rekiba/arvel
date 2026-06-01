"""NullBroadcaster — fail-closed no-op driver."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


class NullBroadcaster:
    """Discards every broadcast. Safe default that never raises."""

    async def broadcast(
        self,
        channels: Sequence[str],
        event: str,
        payload: Mapping[str, object],
        *,
        except_socket_id: str | None = None,
    ) -> None:
        del channels, event, payload, except_socket_id


__all__ = ["NullBroadcaster"]
