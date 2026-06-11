"""Tests for SchedulerSignal and serve_forever() interrupt/pause support."""

from __future__ import annotations

import tempfile
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from arvel.scheduling.signal import SchedulerSignal

if TYPE_CHECKING:
    from arvel.cache.store import CacheStore


def _make_array_store() -> CacheStore:
    from arvel.cache import CacheManager
    from arvel.config.cache_config import CacheConfig, CacheDriver

    cfg = CacheConfig(
        connection=CacheDriver.ARRAY, prefix="signal-test:", file_path=tempfile.gettempdir()
    )
    return CacheManager(cfg).store(None)


class TestSchedulerSignalNoop:
    """All signal methods degrade gracefully when cache facade is unbound."""

    @pytest.mark.asyncio
    async def test_send_interrupt_without_cache_returns_false(self) -> None:
        with patch.object(SchedulerSignal, "_resolve_store", return_value=None):
            sig = SchedulerSignal()
            assert await sig.send_interrupt() is False

    @pytest.mark.asyncio
    async def test_pause_resume_without_cache_return_false(self) -> None:
        with patch.object(SchedulerSignal, "_resolve_store", return_value=None):
            sig = SchedulerSignal()
            assert await sig.pause() is False
            assert await sig.resume() is False

    @pytest.mark.asyncio
    async def test_check_interrupt_without_cache_returns_false(self) -> None:
        with patch.object(SchedulerSignal, "_resolve_store", return_value=None):
            sig = SchedulerSignal()
            assert await sig.check_and_clear_interrupt() is False

    @pytest.mark.asyncio
    async def test_is_paused_without_cache_returns_false(self) -> None:
        with patch.object(SchedulerSignal, "_resolve_store", return_value=None):
            sig = SchedulerSignal()
            assert await sig.is_paused() is False


class TestSchedulerSignalWithCache:
    """Signal round-trips with a real in-memory cache store."""

    @pytest.mark.asyncio
    async def test_interrupt_signal_round_trip(self) -> None:
        store = _make_array_store()
        sig = SchedulerSignal(interrupt_key="arvel:test:interrupt")
        with patch.object(SchedulerSignal, "_resolve_store", return_value=store):
            assert await sig.check_and_clear_interrupt() is False
            assert await sig.send_interrupt() is True
            assert await sig.check_and_clear_interrupt() is True
            # cleared after first check
            assert await sig.check_and_clear_interrupt() is False

    @pytest.mark.asyncio
    async def test_pause_resume_round_trip(self) -> None:
        store = _make_array_store()
        sig = SchedulerSignal(paused_key="arvel:test:paused")
        with patch.object(SchedulerSignal, "_resolve_store", return_value=store):
            assert await sig.is_paused() is False
            assert await sig.pause() is True
            assert await sig.is_paused() is True
            assert await sig.resume() is True
            assert await sig.is_paused() is False


class TestServeForeverSignals:
    """serve_forever() exits on interrupt; skips tasks when paused."""

    @pytest.mark.asyncio
    async def test_interrupt_stops_loop(self) -> None:
        from arvel.scheduling import Schedule, SchedulerKernel

        ran: list[int] = []

        async def task() -> None:
            ran.append(len(ran) + 1)

        schedule = Schedule()
        schedule.call(task).everyMinute()
        kernel = SchedulerKernel(schedule=schedule)

        call_count = 0

        async def _mock_check_interrupt(self: SchedulerSignal) -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 2  # interrupt on second tick

        async def _mock_is_paused(self: SchedulerSignal) -> bool:
            return False

        with (
            patch.object(SchedulerSignal, "check_and_clear_interrupt", _mock_check_interrupt),
            patch.object(SchedulerSignal, "is_paused", _mock_is_paused),
        ):
            await kernel.serve_forever(sleep_seconds=0.01, max_iterations=10)

        # ran once (tick 1 ran tasks, tick 2 interrupted before running)
        assert len(ran) == 1

    @pytest.mark.asyncio
    async def test_pause_skips_tasks(self) -> None:
        from arvel.scheduling import Schedule, SchedulerKernel

        ran: list[int] = []

        async def task() -> None:
            ran.append(1)

        schedule = Schedule()
        schedule.call(task).everyMinute()
        kernel = SchedulerKernel(schedule=schedule)

        tick = 0

        async def _never_interrupt(self: SchedulerSignal) -> bool:
            return False

        async def _paused_first_two(self: SchedulerSignal) -> bool:
            nonlocal tick
            tick += 1
            return tick <= 2

        with (
            patch.object(SchedulerSignal, "check_and_clear_interrupt", _never_interrupt),
            patch.object(SchedulerSignal, "is_paused", _paused_first_two),
        ):
            await kernel.serve_forever(sleep_seconds=0.01, max_iterations=3)

        # only the third tick was unpaused
        assert len(ran) == 1
