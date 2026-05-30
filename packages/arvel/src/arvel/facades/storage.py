"""Storage facade — @classmethod API proxying to the bound StorageManager."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Protocol

if TYPE_CHECKING:
    from arvel.container import Container
    from arvel.storage.disk import StorageDisk
    from arvel.testing.fakes.storage import StorageFakeContext


class StorageManagerLike(Protocol):
    """Minimal surface the Storage facade needs from its bound manager.

    Implemented by ``arvel.storage.StorageManager`` (production) and
    ``arvel.testing.fakes.storage.StorageFake`` (tests).
    """

    def disk(self, name: str | None = None) -> StorageDisk: ...


class Storage:
    """Facade providing a classmethod API for the storage subsystem.

    Bound by ``StorageServiceProvider.register()``.
    """

    _manager: ClassVar[StorageManagerLike | None] = None

    @classmethod
    def bind(cls, container: Container) -> None:
        from arvel.storage import StorageManager

        cls._manager = container.make(StorageManager)

    @classmethod
    def swap_manager(cls, new: StorageManagerLike | None) -> StorageManagerLike | None:
        """Replace the bound manager and return the previous one. Test-only."""
        previous = cls._manager
        cls._manager = new
        return previous

    @classmethod
    def disk(cls, name: str | None = None) -> StorageDisk:
        if cls._manager is None:
            from arvel.cache.exceptions import FacadeNotBoundError

            raise FacadeNotBoundError("Storage")
        return cls._manager.disk(name)

    @classmethod
    def fake(cls, disk: str | None = None) -> StorageFakeContext:
        """Swap in an in-memory StorageFake for tests."""
        from arvel.testing.fakes.storage import StorageFakeContext

        return StorageFakeContext(disk=disk)

    @classmethod
    def assert_exists(cls, path: str, disk: str | None = None) -> None:
        """Assert that ``path`` exists on the fake disk (test-only)."""
        from arvel.testing.fakes.storage import StorageFake

        manager = cls._manager
        if not isinstance(manager, StorageFake):
            raise AssertionError("Storage.assert_exists requires Storage.fake() context")
        if not manager.has_path(path, disk):
            raise AssertionError(f"Storage path {path!r} does not exist")

    @classmethod
    def assert_missing(cls, path: str, disk: str | None = None) -> None:
        """Assert that ``path`` is NOT on the fake disk."""
        from arvel.testing.fakes.storage import StorageFake

        manager = cls._manager
        if not isinstance(manager, StorageFake):
            raise AssertionError("Storage.assert_missing requires Storage.fake() context")
        if manager.has_path(path, disk):
            raise AssertionError(f"Storage path {path!r} exists but should be missing")


__all__ = ["Storage", "StorageManagerLike"]
