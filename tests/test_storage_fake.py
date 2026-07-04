"""FS-RICH (doc 04) — the `Storage.fake` seam: `fake_storage`/`restore_storage` swap a disk for
a temp-dir local one via `FilesystemManager.swap`, and `reset_fakes` restores it in teardown."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from arvel.filesystem import FilesystemManager
from arvel.kernel.application import Application
from arvel.kernel.discovery import bootstrap_providers, clear_cache
from arvel.kernel.globals import app as _app_accessor
from arvel.kernel.globals import set_application
from arvel.testing import FakeFilesystem, fake_storage, reset_fakes, restore_storage


@pytest.fixture(autouse=True)
def _app() -> Any:
    clear_cache()
    app = Application.configure().create()
    bootstrap_providers(app)  # registers FilesystemServiceProvider so "filesystem" resolves
    asyncio.run(app.boot())
    set_application(app)
    yield app
    reset_fakes()
    set_application(None)


def _manager() -> FilesystemManager:
    """The same ``FilesystemManager`` singleton the app container hands ``Storage``."""
    manager: FilesystemManager = _app_accessor("filesystem")
    return manager


async def test_fake_storage_swaps_in_a_temp_dir_disk() -> None:
    fake = fake_storage("local")
    assert isinstance(fake, FakeFilesystem)
    assert _manager().disk("local") is fake._disk  # same instance the manager now hands out

    await fake.assert_missing("a.txt")
    await fake.put("a.txt", b"hello")
    await fake.assert_exists("a.txt")


async def test_assert_count() -> None:
    fake = fake_storage("local")
    await fake.assert_count("uploads", 0)
    await fake.put("uploads/a.txt", b"1")
    await fake.put("uploads/b.txt", b"2")
    await fake.assert_count("uploads", 2)

    with pytest.raises(AssertionError):
        await fake.assert_count("uploads", 5)


async def test_assert_exists_raises_when_missing() -> None:
    fake = fake_storage("local")
    with pytest.raises(AssertionError):
        await fake.assert_exists("nope.txt")


async def test_assert_missing_raises_when_present() -> None:
    fake = fake_storage("local")
    await fake.put("here.txt", b"1")
    with pytest.raises(AssertionError):
        await fake.assert_missing("here.txt")


async def test_restore_storage_reinstates_the_real_driver() -> None:
    manager = _manager()
    real_disk = manager.disk("local")  # cache the real driver first

    fake = fake_storage("local")
    assert manager.disk("local") is fake._disk

    restore_storage("local")
    assert manager.disk("local") is not fake._disk
    assert manager.disk("local") is not real_disk  # reconstructed fresh from config, not cached


async def test_reset_fakes_restores_faked_disks() -> None:
    manager = _manager()
    fake = fake_storage("local")
    assert manager.disk("local") is fake._disk

    reset_fakes()

    assert manager.disk("local") is not fake._disk


async def test_faking_one_disk_leaves_another_untouched() -> None:
    manager = _manager()
    real_local = manager.disk("local")  # cache the real "local" driver first

    fake_storage("s3")  # faking a *different* disk shouldn't disturb the cached "local" one

    assert manager.disk("local") is real_local
