"""Tests for Story 3: Repository Pattern + Epic 13c: Mass Assignment.

Covers: FR-050 through FR-054, NFR-020, NFR-022, NFR-023.
"""

from __future__ import annotations

import pytest
from dirty_equals import IsDatetime, IsPositiveInt

from arvel.data.exceptions import ConfigurationError, NotFoundError
from arvel.data.model import ArvelModel
from arvel.data.repository import Repository

from .conftest import AppTransaction, User  # noqa: TC001


class TestRepositoryFind:
    """FR-050: find(id) returns typed model or raises NotFoundError."""

    async def test_find_existing_user(self, transaction: AppTransaction) -> None:
        async with transaction:
            user = await transaction.users.create({"name": "Alice", "email": "alice@repo.com"})
            found = await transaction.users.find(user.id)
            assert found is not None
            assert isinstance(found, User)
            assert found.name == "Alice"

    async def test_find_nonexistent_raises_not_found(self, transaction: AppTransaction) -> None:
        async with transaction:
            with pytest.raises(NotFoundError):
                await transaction.users.find(99999)


class TestRepositoryCreate:
    """FR-051: create(data) validates, inserts, and returns the model."""

    async def test_create_returns_model_with_id(self, transaction: AppTransaction) -> None:
        async with transaction:
            user = await transaction.users.create({"name": "Bob", "email": "bob@repo.com"})
            assert user.id == IsPositiveInt
            assert user.name == "Bob"
            assert user.email == "bob@repo.com"

    async def test_create_missing_required_column_raises_db_error(
        self, transaction: AppTransaction
    ) -> None:
        """Pydantic schema accepts partial data; DB enforces NOT NULL."""
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError, match="NOT NULL"):
            async with transaction:
                await transaction.users.create({"email": "no-name@repo.com"})

    async def test_create_sets_timestamps(self, transaction: AppTransaction) -> None:
        async with transaction:
            user = await transaction.users.create({"name": "Tim", "email": "tim@repo.com"})
            assert user.created_at == IsDatetime
            assert user.updated_at == IsDatetime


class TestRepositoryUpdate:
    """FR-052: update(id, data) updates only provided fields."""

    async def test_update_changes_specified_fields(self, transaction: AppTransaction) -> None:
        async with transaction:
            user = await transaction.users.create({"name": "Before", "email": "update@repo.com"})
            updated = await transaction.users.update(user.id, {"name": "After"})
            assert updated.name == "After"
            assert updated.email == "update@repo.com"

    async def test_update_nonexistent_raises_not_found(self, transaction: AppTransaction) -> None:
        async with transaction:
            with pytest.raises(NotFoundError):
                await transaction.users.update(99999, {"name": "Ghost"})

    async def test_update_updates_updated_at(self, transaction: AppTransaction) -> None:
        async with transaction:
            user = await transaction.users.create({"name": "TS", "email": "ts@repo.com"})
            original_updated = user.updated_at
            updated = await transaction.users.update(user.id, {"name": "TS2"})
            assert updated.updated_at >= original_updated


class TestRepositoryDelete:
    """FR-053: delete(id) removes record or raises NotFoundError."""

    async def test_delete_existing_user(self, transaction: AppTransaction) -> None:
        async with transaction:
            user = await transaction.users.create({"name": "Delete Me", "email": "del@repo.com"})
            await transaction.users.delete(user.id)
            with pytest.raises(NotFoundError):
                await transaction.users.find(user.id)

    async def test_delete_nonexistent_raises_not_found(self, transaction: AppTransaction) -> None:
        async with transaction:
            with pytest.raises(NotFoundError):
                await transaction.users.delete(99999)


class TestRepositoryCustomQuery:
    """FR-054: Custom query methods use query builder, not raw session."""

    async def test_custom_query_via_query_builder(self, db_session, observer_registry) -> None:
        class CustomUserRepo(Repository[User]):
            async def find_by_email(self, email: str) -> User | None:
                return await self.query().where(User.email == email).order_by(User.id).first()

        repo = CustomUserRepo(session=db_session, observer_registry=observer_registry)
        db_session.add(User(name="Custom", email="custom@repo.com"))
        await db_session.flush()

        user = await repo.find_by_email("custom@repo.com")
        assert user is not None
        assert user.name == "Custom"

    async def test_custom_query_nonexistent(self, db_session, observer_registry) -> None:
        class CustomUserRepo(Repository[User]):
            async def find_by_email(self, email: str) -> User | None:
                return await self.query().where(User.email == email).order_by(User.id).first()

        repo = CustomUserRepo(session=db_session, observer_registry=observer_registry)
        user = await repo.find_by_email("ghost@repo.com")
        assert user is None


class TestMassAssignmentProtection:
    """NFR-022: Only declared column names are accepted in update."""

    async def test_update_ignores_non_column_keys(self, transaction: AppTransaction) -> None:
        async with transaction:
            user = await transaction.users.create({"name": "Safe", "email": "safe@mass.com"})
            updated = await transaction.users.update(
                user.id, {"name": "Still Safe", "_session": "hacked"}
            )
            assert updated.name == "Still Safe"
            assert not hasattr(updated, "_session_hacked")


class TestFillableGuardedProtection:
    """Epic 13c Story 2: Mass-assignment via __fillable__ and __guarded__."""

    async def test_fillable_create_strips_guarded_field(self, transaction: AppTransaction) -> None:
        """Given __fillable__, when create() receives a non-fillable field, it's ignored."""
        async with transaction:
            user = await transaction.fillable_users.create(
                {"name": "Alice", "email": "alice@fill.com", "is_admin": True}
            )
            assert user.name == "Alice"
            assert user.is_admin is False

    async def test_fillable_update_strips_guarded_field(self, transaction: AppTransaction) -> None:
        """Given __fillable__, when update() receives a non-fillable field, it's ignored."""
        async with transaction:
            user = await transaction.fillable_users.create({"name": "Bob", "email": "bob@fill.com"})
            updated = await transaction.fillable_users.update(
                user.id, {"name": "Bobby", "is_admin": True}
            )
            assert updated.name == "Bobby"
            assert updated.is_admin is False

    async def test_fillable_allows_declared_fields(self, transaction: AppTransaction) -> None:
        """Given __fillable__={"name","email","bio"}, all three are assignable."""
        async with transaction:
            user = await transaction.fillable_users.create(
                {"name": "Carol", "email": "carol@fill.com", "bio": "Hello"}
            )
            assert user.bio == "Hello"
            updated = await transaction.fillable_users.update(user.id, {"bio": "Updated bio"})
            assert updated.bio == "Updated bio"

    async def test_guarded_create_strips_guarded_field(self, transaction: AppTransaction) -> None:
        """Given __guarded__, when create() receives a guarded field, it's ignored."""
        async with transaction:
            user = await transaction.guarded_users.create(
                {"name": "Dave", "email": "dave@guard.com", "is_admin": True}
            )
            assert user.name == "Dave"
            assert user.is_admin is False

    async def test_guarded_update_strips_guarded_field(self, transaction: AppTransaction) -> None:
        """Given __guarded__, when update() receives a guarded field, it's ignored."""
        async with transaction:
            user = await transaction.guarded_users.create({"name": "Eve", "email": "eve@guard.com"})
            updated = await transaction.guarded_users.update(
                user.id, {"name": "Evelyn", "is_admin": True}
            )
            assert updated.name == "Evelyn"
            assert updated.is_admin is False

    async def test_guarded_allows_non_guarded_fields(self, transaction: AppTransaction) -> None:
        """Given __guarded__, non-guarded columns are freely assignable."""
        async with transaction:
            user = await transaction.guarded_users.create(
                {"name": "Frank", "email": "frank@guard.com", "bio": "Hi"}
            )
            assert user.bio == "Hi"

    async def test_default_strips_pk_and_timestamps(self, transaction: AppTransaction) -> None:
        """Given neither __fillable__ nor __guarded__, PK and timestamps are excluded."""
        async with transaction:
            user = await transaction.users.create({"name": "Grace", "email": "grace@def.com"})
            updated = await transaction.users.update(user.id, {"name": "Updated", "id": 99999})
            assert updated.name == "Updated"
            assert updated.id != 99999

    async def test_strict_mode_logs_warning(
        self,
        transaction: AppTransaction,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Strict mass-assign mode logs warning for guarded fields."""
        monkeypatch.setenv("ARVEL_STRICT_MASS_ASSIGN", "true")
        warning_calls: list[tuple[str, str, str]] = []

        def _capture_warning(message: str, model_name: str, key: str) -> None:
            warning_calls.append((message, model_name, key))

        class _LoggerStub:
            def warning(self, message: str, model_name: str, key: str) -> None:
                _capture_warning(message, model_name, key)

        import arvel.data._mass_assign as mass_assign_module

        monkeypatch.setattr(mass_assign_module, "_logger", _LoggerStub())

        async with transaction:
            user = await transaction.fillable_users.create(
                {"name": "Hank", "email": "hank@strict.com"}
            )
            await transaction.fillable_users.update(user.id, {"name": "Henry", "is_admin": True})

        assert len(warning_calls) == 1
        message, model_name, key = warning_calls[0]
        assert "Mass-assignment blocked (strict mode)" in message
        assert model_name == "FillableUser"
        assert key == "is_admin"

    def test_both_fillable_and_guarded_raises_configuration_error(self) -> None:
        """Both __fillable__ and __guarded__ raises ConfigurationError."""
        from sqlalchemy import String
        from sqlalchemy.orm import Mapped, mapped_column  # noqa: TC002 — runtime use

        with pytest.raises(ConfigurationError, match="both __fillable__ and __guarded__"):

            class BadModel(ArvelModel):
                __tablename__ = "bad_models"
                __fillable__: set[str] = {"name"}  # noqa: RUF012
                __guarded__: set[str] = {"id"}  # noqa: RUF012

                id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
                name: Mapped[str] = mapped_column(String(100))


class TestSessionEncapsulation:
    """NFR-023: SA sessions never leak above repository layer."""

    def test_repository_has_no_public_session_attr(self) -> None:
        assert not hasattr(Repository, "session")

    def test_repository_session_is_private(self) -> None:
        assert "session" not in vars(Repository)
        all_names = Repository.__init__.__code__.co_varnames + Repository.__init__.__code__.co_names
        assert any(name.startswith("_") and "session" in name for name in all_names)


class TestRepositorySessionResolver:
    """Repository resolves session from ArvelModel when not passed explicitly."""

    def test_no_session_no_resolver_raises(self) -> None:
        from .conftest import UserRepository

        ArvelModel.clear_session_resolver()
        with pytest.raises(RuntimeError, match="No session provided"):
            UserRepository()

    async def test_no_session_uses_resolver(self, db_session) -> None:
        from .conftest import UserRepository

        ArvelModel.set_session_resolver(lambda: db_session)
        try:
            repo = UserRepository()
            users = await repo.all()
            assert isinstance(users, list)
        finally:
            ArvelModel.clear_session_resolver()

    async def test_explicit_session_ignores_resolver(self, db_session) -> None:
        from arvel.data.observer import ObserverRegistry

        from .conftest import UserRepository

        called = False

        def bad_resolver():
            nonlocal called
            called = True
            return db_session

        ArvelModel.set_session_resolver(bad_resolver)
        try:
            repo = UserRepository(session=db_session, observer_registry=ObserverRegistry())
            await repo.all()
            assert not called
        finally:
            ArvelModel.clear_session_resolver()
