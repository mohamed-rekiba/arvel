"""Tests for QueueServiceProvider"""

from __future__ import annotations

import pytest
from arvel import Application
from arvel.facades.bus import Bus as BusFacade
from arvel.queue.manager import QueueManager
from arvel.queue.providers.queue_service_provider import QueueServiceProvider


class TestQueueServiceProvider:
    """QueueServiceProvider registers QueueManager and Bus."""

    def test_register_binds_queue_manager(self) -> None:
        app = Application()
        provider = QueueServiceProvider(app)
        provider.register()
        manager = app.container.make(QueueManager)
        assert isinstance(manager, QueueManager)

    def test_register_binds_bus(self) -> None:
        from arvel.queue.bus import Bus

        app = Application()
        provider = QueueServiceProvider(app)
        provider.register()
        bus = app.container.make(Bus)
        assert isinstance(bus, Bus)

    @pytest.mark.asyncio
    async def test_boot_binds_bus_facade(self) -> None:
        app = Application()
        provider = QueueServiceProvider(app)
        provider.register()
        await provider.boot()
        assert BusFacade.manager is not None

    @pytest.mark.asyncio
    async def test_shutdown_calls_driver_close(self) -> None:
        """Provider shutdown cleans up driver connections."""
        app = Application()
        provider = QueueServiceProvider(app)
        provider.register()
        await provider.boot()
        await provider.shutdown()  # should not raise

    def test_commands_returns_queue_commands(self) -> None:
        app = Application()
        provider = QueueServiceProvider(app)
        provider.register()  # must be called first to bind FailedJobStore
        cmds = provider.commands()
        cmd_names = [c.name for c in cmds]
        assert "queue:work" in cmd_names
        assert "queue:failed" in cmd_names
        assert "queue:retry" in cmd_names
        assert "queue:flush" in cmd_names
        assert "queue:forget" in cmd_names

    @pytest.mark.asyncio
    async def test_queue_work_command_receives_failed_job_store(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """provider-created workers must persist exhausted jobs."""
        from arvel.queue.commands.queue_work import QueueWorkCommand
        from arvel.queue.failed_job_store import FailedJobStore

        captured: dict[str, object | None] = {}

        class RecordingWorker:
            def __init__(
                self,
                manager: QueueManager,
                *,
                queue: str,
                failed_job_store: object | None,
                restart_signal: object | None = None,
            ) -> None:
                captured["failed_job_store"] = failed_job_store
                captured["restart_signal"] = restart_signal

            async def drain_then_stop(self) -> None:
                return None

        monkeypatch.setattr(
            "arvel.queue.commands.queue_work.Worker",
            RecordingWorker,
        )

        app = Application()
        provider = QueueServiceProvider(app)
        provider.register()

        commands = provider.commands()
        queue_work = next(cmd for cmd in commands if isinstance(cmd, QueueWorkCommand))
        await queue_work.run_worker(queue="default", stop_when_empty=True)

        from arvel.queue.restart import QueueRestartSignal

        assert isinstance(captured["failed_job_store"], FailedJobStore)
        assert isinstance(captured["restart_signal"], QueueRestartSignal), (
            "QueueWorkCommand must pass a live QueueRestartSignal to Worker so "
            "queue:restart can reach this worker."
        )
