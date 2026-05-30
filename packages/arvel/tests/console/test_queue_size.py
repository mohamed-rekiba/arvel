"""Tests for queue:size command."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arvel.queue.commands.queue_size import QueueSizeCommand


class TestQueueSizeCommand:
    """queue:size delegates to connection().size() and prints the result."""

    @pytest.mark.asyncio
    async def test_size_printed(self) -> None:
        conn = MagicMock()
        conn.size = AsyncMock(return_value=7)

        manager = MagicMock()
        manager.connection.return_value = conn

        cmd = QueueSizeCommand(manager)
        with patch("typer.echo") as mock_echo:
            await cmd.show_size("default")

        mock_echo.assert_called_once()
        assert "7" in mock_echo.call_args[0][0]

    @pytest.mark.asyncio
    async def test_custom_queue_name_passed_to_size(self) -> None:
        conn = MagicMock()
        conn.size = AsyncMock(return_value=0)

        manager = MagicMock()
        manager.connection.return_value = conn

        cmd = QueueSizeCommand(manager)
        with patch("typer.echo"):
            await cmd.show_size("emails")

        conn.size.assert_awaited_once_with("emails")

    def test_command_registered_with_correct_name(self) -> None:
        manager = MagicMock()
        manager.connection.return_value = MagicMock()

        cmd = QueueSizeCommand(manager)
        assert cmd.name == "queue:size"
