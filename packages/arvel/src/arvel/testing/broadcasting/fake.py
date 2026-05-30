"""BroadcasterFake — records calls; satisfies the Broadcaster Protocol (FR-013-014)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RecordedBroadcast:
    channels: list[str]
    event: str
    payload: dict[str, object]
    except_socket_id: str | None = None


@dataclass
class BroadcasterFake:
    """In-memory broadcaster for tests.

    Use `Broadcast.set_manager(...)` (or inject directly) to swap into prod code.
    """

    calls: list[RecordedBroadcast] = field(default_factory=list[RecordedBroadcast])

    async def broadcast(
        self,
        channels: Sequence[str],
        event: str,
        payload: Mapping[str, object],
        *,
        except_socket_id: str | None = None,
    ) -> None:
        self.calls.append(
            RecordedBroadcast(
                channels=list(channels),
                event=event,
                payload=dict(payload),
                except_socket_id=except_socket_id,
            ),
        )

    def assert_broadcasted(self, event: str) -> None:
        hits = [c for c in self.calls if c.event == event]
        if not hits:
            raise AssertionError(
                f"Expected event {event!r} to be broadcasted; "
                f"recorded events were: {[c.event for c in self.calls]}",
            )

    def assert_broadcasted_on(self, channel: str, event: str) -> None:
        hits = [c for c in self.calls if c.event == event and channel in c.channels]
        if not hits:
            raise AssertionError(
                f"Expected event {event!r} to be broadcasted on channel {channel!r}; "
                f"recorded: {[(c.event, c.channels) for c in self.calls]}",
            )

    def assert_nothing_broadcasted(self) -> None:
        if self.calls:
            raise AssertionError(
                f"Expected no broadcasts; got {len(self.calls)}: "
                f"{[(c.event, c.channels) for c in self.calls]}",
            )


__all__ = ["BroadcasterFake", "RecordedBroadcast"]
