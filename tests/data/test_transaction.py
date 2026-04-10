"""Tests for Story 4: Transaction (database transactions).

Covers: FR-055 through FR-060, NFR-024.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from dirty_equals import IsPositiveInt

from arvel.data.transaction import Transaction

from .conftest import AppTransaction, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from arvel.data.observer import ObserverRegistry


class TestTransactionContextManager:
    """FR-055: async with tx begins a transaction."""

    async def test_transaction_context_manager_works(self, transaction: AppTransaction) -> None:
        async with transaction:
            user = await transaction.users.create({"name": "TX", "email": "tx@test.com"})
            assert user.id == IsPositiveInt


class TestTransactionAtomicCommit:
    """FR-056: Normal exit commits all changes atomically."""

    async def test_multiple_writes_committed(
        self, db_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        tx = AppTransaction(session=db_session, observer_registry=observer_registry)
        async with tx:
            user = await tx.users.create({"name": "Author", "email": "author@tx.com"})
            await tx.posts.create({"title": "First Post", "user_id": user.id})

        found_user = await tx.users.find(user.id)
        assert found_user is not None


class TestTransactionRollback:
    """FR-057: Exception inside transaction block rolls back all changes."""

    async def test_exception_rolls_back(
        self, db_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        tx = AppTransaction(session=db_session, observer_registry=observer_registry)

        with pytest.raises(ValueError, match="intentional"):
            async with tx:
                await tx.users.create({"name": "Ghost", "email": "ghost@tx.com"})
                raise ValueError("intentional failure")

        count = await User.query(db_session).count()
        assert count == 0


class TestTransactionNestedSavepoint:
    """FR-058: Nested transaction uses SAVEPOINTs."""

    async def test_inner_failure_doesnt_rollback_outer(
        self, db_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        tx = AppTransaction(session=db_session, observer_registry=observer_registry)

        async with tx:
            await tx.users.create({"name": "Outer", "email": "outer@tx.com"})

            try:
                async with tx.nested():
                    await tx.users.create({"name": "Inner", "email": "inner@tx.com"})
                    raise ValueError("inner failure")
            except ValueError:
                pass

        results = await User.query(db_session).all()
        names = [u.name for u in results]
        assert "Outer" in names
        assert "Inner" not in names


class TestTransactionSharedSession:
    """FR-059: Multiple repositories share the same session via transaction."""

    async def test_repos_share_session(self, transaction: AppTransaction) -> None:
        async with transaction:
            user = await transaction.users.create({"name": "Shared", "email": "shared@tx.com"})
            post = await transaction.posts.create({"title": "Shared Post", "user_id": user.id})
            assert user.id is not None
            assert post.user_id == user.id


class TestTransactionSessionNotExposed:
    """FR-060: Transaction does not expose raw session publicly."""

    def test_no_public_session_attribute(self) -> None:
        assert not hasattr(Transaction, "session")

    def test_session_is_private(self, transaction: AppTransaction) -> None:
        assert hasattr(transaction, "_session")
        assert not hasattr(transaction, "session")


class TestTransactionAtomicity:
    """NFR-024: Atomic commits — no partial writes."""

    async def test_partial_failure_rolls_back_all(
        self, db_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        tx = AppTransaction(session=db_session, observer_registry=observer_registry)

        with pytest.raises(Exception):  # noqa: B017
            async with tx:
                await tx.users.create({"name": "First", "email": "first@atom.com"})
                await tx.users.create({"name": "First", "email": "first@atom.com"})

        count = await User.query(db_session).count()
        assert count == 0


class TestTransactionSessionResolver:
    """Transaction resolves session from ArvelModel when not passed explicitly."""

    def test_no_session_no_resolver_raises(self) -> None:
        from arvel.data.model import ArvelModel

        ArvelModel.clear_session_resolver()
        with pytest.raises(RuntimeError, match="No session provided"):
            AppTransaction()

    async def test_no_session_uses_resolver(self, db_session: AsyncSession) -> None:
        from arvel.data.model import ArvelModel

        ArvelModel.set_session_resolver(lambda: db_session)
        try:
            tx = AppTransaction()
            async with tx:
                user = await tx.users.create({"name": "Resolved", "email": "resolved@tx.com"})
                assert user.id is not None
        finally:
            ArvelModel.clear_session_resolver()

    async def test_explicit_session_ignores_resolver(
        self, db_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        from arvel.data.model import ArvelModel

        called = False

        def bad_resolver():
            nonlocal called
            called = True
            return db_session

        ArvelModel.set_session_resolver(bad_resolver)
        try:
            tx = AppTransaction(session=db_session, observer_registry=observer_registry)
            async with tx:
                user = await tx.users.create({"name": "Explicit", "email": "explicit@tx.com"})
                assert user.id is not None
            assert not called
        finally:
            ArvelModel.clear_session_resolver()
