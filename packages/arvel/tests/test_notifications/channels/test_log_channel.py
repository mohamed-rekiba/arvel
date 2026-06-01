"""Tests for LogChannel."""

from __future__ import annotations

import pytest
from arvel.notifications.channels.log_channel import LogChannel

from test_notifications.helpers import (  # type: ignore[import-not-found]
    FakeUser,
    WelcomeNotification,
)


class TestLogChannel:
    @pytest.mark.asyncio
    async def test_never_raises(self) -> None:
        channel = LogChannel()
        await channel.send(FakeUser(1), WelcomeNotification())  # must not raise

    @pytest.mark.asyncio
    async def test_broadcast_channel_stub_logs_warning(self) -> None:
        """broadcast channel is a stub that logs a warning."""
        from arvel.notifications.channels.broadcast_channel import BroadcastChannel

        channel = BroadcastChannel()
        await channel.send(FakeUser(1), WelcomeNotification())  # must not raise
