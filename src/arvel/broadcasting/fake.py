"""BroadcastFake — testing double that captures broadcasts for assertion."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arvel.broadcasting.contracts import BroadcastContract

if TYPE_CHECKING:
    from arvel.broadcasting.channels import Channel


class BroadcastFake(BroadcastContract):
    """Captures all broadcasts for test assertions.

    Use in tests to replace the real broadcaster and verify that events
    were broadcast to the correct channels.
    """

    def __init__(self) -> None:
        self._broadcasts: list[dict[str, Any]] = []

    @property
    def broadcast_count(self) -> int:
        return len(self._broadcasts)

    async def broadcast(
        self,
        channels: list[Channel],
        event: str,
        data: dict[str, Any],
    ) -> None:
        self._broadcasts.append(
            {
                "channels": [ch.name for ch in channels],
                "event": event,
                "data": data,
            }
        )

    def assert_broadcast(
        self,
        event_name: str,
        *,
        channel: str | None = None,
    ) -> None:
        """Assert that an event with *event_name* was broadcast.

        Optionally filter by *channel* name.
        """
        for entry in self._broadcasts:
            if entry["event"] == event_name and (channel is None or channel in entry["channels"]):
                return
        msg = f"Expected '{event_name}' to be broadcast, but it was never broadcast"
        if channel:
            msg += f" on channel '{channel}'"
        raise AssertionError(msg)

    def assert_broadcast_on(self, channel: str) -> None:
        """Assert that any event was broadcast to *channel*."""
        for entry in self._broadcasts:
            if channel in entry["channels"]:
                return
        msg = f"No broadcast found on channel '{channel}'"
        raise AssertionError(msg)

    def assert_nothing_broadcast(self) -> None:
        """Assert that no events were broadcast."""
        if self._broadcasts:
            events = {e["event"] for e in self._broadcasts}
            msg = f"Expected no broadcasts, but got {len(self._broadcasts)}: {events}"
            raise AssertionError(msg)

    def assert_broadcast_count(self, event_name: str, expected: int) -> None:
        """Assert that *event_name* was broadcast exactly *expected* times."""
        actual = sum(1 for e in self._broadcasts if e["event"] == event_name)
        if actual != expected:
            msg = f"Expected {expected} broadcasts of '{event_name}', but got {actual}"
            raise AssertionError(msg)
