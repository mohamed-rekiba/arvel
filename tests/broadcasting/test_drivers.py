"""Tests for broadcast drivers — FR-002.

FR-002: NullBroadcaster, MemoryBroadcaster, LogBroadcaster.
"""

from __future__ import annotations

from arvel.broadcasting.channels import Channel, PrivateChannel


class TestNullBroadcaster:
    """FR-002: Null driver does nothing."""

    async def test_broadcast_does_nothing(self) -> None:
        from arvel.broadcasting.drivers.null_driver import NullBroadcaster

        broadcaster = NullBroadcaster()
        await broadcaster.broadcast([Channel("news")], "test.event", {"key": "value"})

    async def test_null_is_broadcast_contract(self) -> None:
        from arvel.broadcasting.contracts import BroadcastContract
        from arvel.broadcasting.drivers.null_driver import NullBroadcaster

        assert isinstance(NullBroadcaster(), BroadcastContract)


class TestMemoryBroadcaster:
    """FR-002: Memory driver stores broadcasts for retrieval."""

    async def test_broadcast_stores_events(self) -> None:
        from arvel.broadcasting.drivers.memory_driver import MemoryBroadcaster

        broadcaster = MemoryBroadcaster()
        channels = [Channel("news")]
        await broadcaster.broadcast(channels, "article.published", {"id": 1})

        assert len(broadcaster.broadcasts) == 1
        entry = broadcaster.broadcasts[0]
        assert entry["event"] == "article.published"
        assert entry["data"] == {"id": 1}

    async def test_broadcast_records_channel_names(self) -> None:
        from arvel.broadcasting.drivers.memory_driver import MemoryBroadcaster

        broadcaster = MemoryBroadcaster()
        channels = [Channel("news"), PrivateChannel("orders.42")]
        await broadcaster.broadcast(channels, "test", {})

        entry = broadcaster.broadcasts[0]
        assert entry["channels"] == ["news", "orders.42"]

    async def test_flush_clears_broadcasts(self) -> None:
        from arvel.broadcasting.drivers.memory_driver import MemoryBroadcaster

        broadcaster = MemoryBroadcaster()
        await broadcaster.broadcast([Channel("x")], "e", {})
        broadcaster.flush()
        assert len(broadcaster.broadcasts) == 0

    async def test_memory_is_broadcast_contract(self) -> None:
        from arvel.broadcasting.contracts import BroadcastContract
        from arvel.broadcasting.drivers.memory_driver import MemoryBroadcaster

        assert isinstance(MemoryBroadcaster(), BroadcastContract)


class TestLogBroadcaster:
    """FR-002: Log driver outputs broadcasts via structlog."""

    async def test_broadcast_logs_event(self) -> None:
        from arvel.broadcasting.drivers.log_driver import LogBroadcaster

        broadcaster = LogBroadcaster()
        await broadcaster.broadcast([Channel("news")], "test.event", {"key": "val"})

    async def test_log_is_broadcast_contract(self) -> None:
        from arvel.broadcasting.contracts import BroadcastContract
        from arvel.broadcasting.drivers.log_driver import LogBroadcaster

        assert isinstance(LogBroadcaster(), BroadcastContract)
