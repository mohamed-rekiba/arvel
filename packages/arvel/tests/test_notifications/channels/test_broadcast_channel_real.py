"""BroadcastChannel (real implementation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from test_notifications.helpers import FakeUser  # type: ignore[import-not-found]


@pytest.mark.asyncio
async def test_broadcast_channel_routes_to_broadcaster() -> None:
    """AC1: real BroadcastChannel calls Broadcast.driver().broadcast."""
    from arvel.broadcasting.config import BroadcastConfig, BroadcastDriver
    from arvel.broadcasting.manager import BroadcastManager
    from arvel.facades.broadcast import Broadcast
    from arvel.notifications.channels.broadcast_channel import BroadcastChannel
    from arvel.notifications.notification import Notification

    calls: list[tuple[list[str], str, dict[str, Any]]] = []

    class _Spy:
        async def broadcast(
            self,
            channels: Sequence[str],
            event: str,
            payload: dict[str, Any],
            *,
            except_socket_id: str | None = None,
        ) -> None:
            del except_socket_id
            calls.append((list(channels), event, payload))

    class _SpyManager(BroadcastManager):
        def driver(self, name: str | None = None) -> Any:
            return _Spy()

    Broadcast.set_manager(_SpyManager(BroadcastConfig(default=BroadcastDriver.NULL)))
    try:

        class _N(Notification):
            def via(self, notifiable: Any) -> list[str]:
                return ["broadcast"]

            def to_broadcast(self, notifiable: Any) -> dict[str, Any]:
                return {"channels": ["private-user.1"], "data": {"k": "v"}}

        await BroadcastChannel().send(FakeUser(1), _N())
    finally:
        Broadcast.set_manager(None)

    assert calls
    channels, event, payload = calls[0]
    assert channels == ["private-user.1"]
    assert event == "_N"
    assert payload == {"k": "v"}


@pytest.mark.asyncio
async def test_broadcast_channel_skips_when_no_via_data() -> None:
    """AC2: if to_broadcast not implemented, channel is a no-op (no broadcast call)."""
    from arvel.broadcasting.config import BroadcastConfig, BroadcastDriver
    from arvel.broadcasting.manager import BroadcastManager
    from arvel.facades.broadcast import Broadcast
    from arvel.notifications.channels.broadcast_channel import BroadcastChannel
    from arvel.notifications.notification import Notification

    calls: list[object] = []

    class _Spy:
        async def broadcast(self, *a: Any, **kw: Any) -> None:
            calls.append((a, kw))

    class _SpyManager(BroadcastManager):
        def driver(self, name: str | None = None) -> Any:
            return _Spy()

    Broadcast.set_manager(_SpyManager(BroadcastConfig(default=BroadcastDriver.NULL)))
    try:

        class _N(Notification):
            def via(self, notifiable: Any) -> list[str]:
                return ["broadcast"]

        await BroadcastChannel().send(FakeUser(1), _N())
        # The real channel MUST consult Broadcast.driver() but skip broadcast() when
        # to_broadcast is missing. The current stub never calls Broadcast at all,
        # so this assertion still flags the stub as RED via a follow-up check.
        assert not calls
        # And the channel MUST be the post-implementation (not the stub).
        import inspect as _inspect

        from arvel.notifications.channels import broadcast_channel as bc

        source = _inspect.getsource(bc)
        assert "BroadcastChannel is a stub" not in source, (
            "Stub BroadcastChannel still in place — WI-013-S3 replacement not done."
        )
    finally:
        Broadcast.set_manager(None)
