"""Tests for Story 5: Model Lifecycle Events (Observer).

Covers: FR-061 through FR-066, NFR-025.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from arvel.data.exceptions import CreationAbortedError
from arvel.data.observer import ModelObserver, ObserverRegistry  # noqa: TC001

from .conftest import AppTransaction, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class _TrackingObserver(ModelObserver):
    """Observer that records which hooks fired and in what order."""

    def __init__(self) -> None:
        self.events: list[str] = []

    async def creating(self, instance: Any) -> bool:
        self.events.append("creating")
        return True

    async def created(self, instance: Any) -> None:
        self.events.append("created")

    async def updating(self, instance: Any) -> bool:
        self.events.append("updating")
        return True

    async def updated(self, instance: Any) -> None:
        self.events.append("updated")

    async def deleting(self, instance: Any) -> bool:
        self.events.append("deleting")
        return True

    async def deleted(self, instance: Any) -> None:
        self.events.append("deleted")


class _AbortingObserver(ModelObserver):
    """Observer that aborts creation."""

    async def creating(self, instance: Any) -> bool:
        return False


class TestObserverCreatingCreated:
    """FR-061: creating/created hooks fire on model creation."""

    async def test_creating_and_created_fire(
        self, transaction: AppTransaction, observer_registry: ObserverRegistry
    ) -> None:
        tracker = _TrackingObserver()
        observer_registry.register(User, tracker)

        async with transaction:
            await transaction.users.create({"name": "Observed", "email": "obs@test.com"})

        assert "creating" in tracker.events
        assert "created" in tracker.events
        assert tracker.events.index("creating") < tracker.events.index("created")


class TestObserverCreatingAbort:
    """FR-062: creating returning False aborts the creation."""

    async def test_creating_false_aborts(
        self, transaction: AppTransaction, observer_registry: ObserverRegistry
    ) -> None:
        aborter = _AbortingObserver()
        observer_registry.register(User, aborter)

        async with transaction:
            with pytest.raises(CreationAbortedError):
                await transaction.users.create({"name": "Aborted", "email": "abort@test.com"})


class TestObserverPriorityOrdering:
    """FR-063: Multiple observers execute in priority order."""

    async def test_priority_ordering(
        self, transaction: AppTransaction, observer_registry: ObserverRegistry
    ) -> None:
        order: list[str] = []

        class ObsA(ModelObserver):
            async def creating(self, instance: Any) -> bool:
                order.append("A")
                return True

        class ObsB(ModelObserver):
            async def creating(self, instance: Any) -> bool:
                order.append("B")
                return True

        observer_registry.register(User, ObsA(), priority=20)
        observer_registry.register(User, ObsB(), priority=10)

        async with transaction:
            await transaction.users.create({"name": "Priority", "email": "pri@test.com"})

        assert order == ["B", "A"]


class TestObserverCrossModule:
    """FR-064: Cross-module observation via string name."""

    async def test_observe_by_model_name(
        self, transaction: AppTransaction, observer_registry: ObserverRegistry
    ) -> None:
        tracker = _TrackingObserver()
        observer_registry.register("User", tracker)

        async with transaction:
            await transaction.users.create({"name": "CrossMod", "email": "cross@test.com"})

        assert "created" in tracker.events


class TestObserverAllLifecycleEvents:
    """FR-065: All 6 lifecycle events are supported."""

    async def test_all_events_fire(
        self, transaction: AppTransaction, observer_registry: ObserverRegistry
    ) -> None:
        tracker = _TrackingObserver()
        observer_registry.register(User, tracker)

        async with transaction:
            user = await transaction.users.create({"name": "Full", "email": "full@test.com"})
            await transaction.users.update(user.id, {"name": "Updated"})
            await transaction.users.delete(user.id)

        assert tracker.events == [
            "creating",
            "created",
            "updating",
            "updated",
            "deleting",
            "deleted",
        ]


class TestObserverTransactionBoundary:
    """FR-066: Observers execute within the transaction boundary."""

    async def test_observer_error_triggers_rollback(
        self, db_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        class FailingObserver(ModelObserver):
            async def created(self, instance: Any) -> None:
                raise RuntimeError("observer failure")

        observer_registry.register(User, FailingObserver())
        tx = AppTransaction(session=db_session, observer_registry=observer_registry)

        with pytest.raises(RuntimeError, match="observer failure"):
            async with tx:
                await tx.users.create({"name": "FailObs", "email": "failobs@test.com"})

        count = await User.query(db_session).count()
        assert count == 0


class TestObserverExceptionPropagation:
    """NFR-025: Observer exceptions propagate and trigger rollback."""

    async def test_post_hook_exception_propagates(
        self, db_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        class BrokenUpdated(ModelObserver):
            async def updated(self, instance: Any) -> None:
                raise ValueError("broken updated hook")

        observer_registry.register(User, BrokenUpdated())
        tx = AppTransaction(session=db_session, observer_registry=observer_registry)

        with pytest.raises(ValueError, match="broken updated hook"):
            async with tx:
                user = await tx.users.create({"name": "Hook", "email": "hook@test.com"})
                await tx.users.update(user.id, {"name": "Broken"})
