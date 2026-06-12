"""SchedulerServiceProvider boot discovery."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from arvel.providers.scheduler_provider import SchedulerServiceProvider
from arvel.scheduling import Schedule

if TYPE_CHECKING:
    from arvel.application import Application


class _Container:
    def __init__(self) -> None:
        self.schedule = Schedule()

    def make(self, key: type[Schedule]) -> Schedule:
        assert key is Schedule
        return self.schedule


class _App:
    def __init__(self, base: Path) -> None:
        self.container = _Container()
        self._base = base

    def base_path(self) -> Path:
        return self._base


def _provider(base: Path) -> SchedulerServiceProvider:
    return SchedulerServiceProvider(cast("Application", _App(base)))


async def test_scheduler_provider_boot_returns_without_kernel_file(tmp_path: Path) -> None:
    await _provider(tmp_path).boot()


async def test_scheduler_provider_boot_returns_without_kernel_class(tmp_path: Path) -> None:
    kernel_dir = tmp_path / "app" / "Console"
    kernel_dir.mkdir(parents=True)
    (kernel_dir / "Kernel.py").write_text("VALUE = 1\n")

    await _provider(tmp_path).boot()


async def test_scheduler_provider_boot_propagates_kernel_errors(tmp_path: Path) -> None:
    """A broken Kernel.schedule() fails boot loudly instead of an empty schedule."""
    kernel_dir = tmp_path / "app" / "Console"
    kernel_dir.mkdir(parents=True)
    (kernel_dir / "Kernel.py").write_text(
        "class Kernel:\n"
        "    def schedule(self, schedule):\n"
        "        raise RuntimeError('bad kernel')\n"
    )

    with pytest.raises(RuntimeError, match="bad kernel"):
        await _provider(tmp_path).boot()


def test_scheduler_provider_commands() -> None:
    commands = SchedulerServiceProvider.commands(_provider(Path()))

    assert [command.name for command in commands] == [
        "schedule:work",
        "schedule:list",
        "schedule:interrupt",
        "schedule:pause",
        "schedule:continue",
    ]
