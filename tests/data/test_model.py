"""Tests for Story 1: ArvelModel — SA DeclarativeBase + Pydantic schema auto-gen.

Covers: FR-039 through FR-043, NFR-028.
"""

from __future__ import annotations

import pytest
from dirty_equals import IsDatetime
from sqlalchemy import Table

from arvel.data.model import ArvelModel
from arvel.data.observer import ModelObserver
from tests._fixtures.models import (
    AppendedUser,
    CastUser,
    HiddenUser,
    MutatorUser,
    VisibleUser,
)

from .conftest import FillableUser, Post, User


class TestArvelModelTableMapping:
    """FR-039: ArvelModel generates SA table mapping + Pydantic schema."""

    def test_user_has_sa_table_metadata(self) -> None:
        assert hasattr(User, "__table__")
        assert isinstance(User.__table__, Table)
        assert User.__table__.name == "users"

    def test_post_has_sa_table_metadata(self) -> None:
        assert hasattr(Post, "__table__")
        assert isinstance(Post.__table__, Table)
        assert Post.__table__.name == "posts"

    def test_user_has_pydantic_schema(self) -> None:
        schema = User.__pydantic_model__
        assert schema is not None
        assert hasattr(schema, "model_validate")

    def test_post_has_pydantic_schema(self) -> None:
        schema = Post.__pydantic_model__
        assert schema is not None

    def test_model_is_arvel_model_subclass(self) -> None:
        assert issubclass(User, ArvelModel)
        assert issubclass(Post, ArvelModel)


class TestColumnTypeInference:
    """FR-040: Pydantic-typed fields infer correct SA column types."""

    def test_string_field_maps_to_string_column(self) -> None:
        col = User.__table__.c.name
        assert col is not None
        assert str(col.type) in ("VARCHAR(100)", "VARCHAR")

    def test_integer_field_maps_to_integer_column(self) -> None:
        col = User.__table__.c.age
        assert col is not None

    def test_boolean_field_maps_to_boolean_column(self) -> None:
        col = User.__table__.c.active
        assert col is not None

    def test_text_field_maps_to_text_column(self) -> None:
        col = Post.__table__.c.body
        assert col is not None

    def test_foreign_key_column_exists(self) -> None:
        col = Post.__table__.c.user_id
        assert len(col.foreign_keys) == 1


class TestNullableFields:
    """FR-041: Optional fields map to nullable columns."""

    def test_optional_field_is_nullable(self) -> None:
        col = User.__table__.c.age
        assert col.nullable is True

    def test_required_field_is_not_nullable(self) -> None:
        col = User.__table__.c.name
        assert col.nullable is False

    def test_optional_text_is_nullable(self) -> None:
        col = Post.__table__.c.body
        assert col.nullable is True


class TestPydanticValidation:
    """FR-042: model_validate runs Pydantic validation."""

    def test_model_validate_with_valid_data(self) -> None:
        schema = User.__pydantic_model__
        validated = schema.model_validate({"name": "Alice", "email": "alice@example.com"})
        data = validated.model_dump()
        assert data["name"] == "Alice"
        assert data["email"] == "alice@example.com"

    def test_model_validate_accepts_partial_data(self) -> None:
        """All schema fields are optional — DB enforces NOT NULL at insert time."""
        schema = User.__pydantic_model__
        validated = schema.model_validate({"email": "alice@example.com"})
        data = validated.model_dump()
        assert data["email"] == "alice@example.com"
        assert data["name"] is None

    def test_model_validate_accepts_optional_none(self) -> None:
        schema = User.__pydantic_model__
        validated = schema.model_validate(
            {"name": "Alice", "email": "alice@example.com", "age": None}
        )
        assert validated.model_dump()["age"] is None


class TestModelDump:
    """FR-043: model_dump returns Pydantic v2 serialization."""

    async def test_model_dump_returns_dict(self, db_session) -> None:
        user = User(name="Bob", email="bob@example.com", age=30)
        db_session.add(user)
        await db_session.flush()

        result = user.model_dump()
        assert isinstance(result, dict)
        assert result["name"] == "Bob"
        assert result["email"] == "bob@example.com"

    async def test_model_dump_exclude_fields(self, db_session) -> None:
        user = User(name="Bob", email="bob@example.com")
        db_session.add(user)
        await db_session.flush()

        result = user.model_dump(exclude={"email"})
        assert "email" not in result
        assert "name" in result

    async def test_model_dump_include_fields(self, db_session) -> None:
        user = User(name="Bob", email="bob@example.com")
        db_session.add(user)
        await db_session.flush()

        result = user.model_dump(include={"name"})
        assert "name" in result
        assert "email" not in result


class TestNoSQLModelDependency:
    """NFR-028: Zero imports from sqlmodel."""

    def test_arvel_model_does_not_import_sqlmodel(self) -> None:
        import sys

        assert "sqlmodel" not in sys.modules


class TestTimestampFields:
    """Models support created_at / updated_at auto-timestamps (Story 2 overlap)."""

    def test_user_has_created_at_column(self) -> None:
        assert "created_at" in User.__table__.c

    def test_user_has_updated_at_column(self) -> None:
        assert "updated_at" in User.__table__.c

    async def test_created_at_set_on_insert(self, db_session) -> None:
        user = User(name="Charlie", email="charlie@example.com")
        db_session.add(user)
        await db_session.flush()
        assert user.created_at == IsDatetime

    async def test_updated_at_set_on_insert(self, db_session) -> None:
        user = User(name="Charlie", email="charlie2@example.com")
        db_session.add(user)
        await db_session.flush()
        assert user.updated_at == IsDatetime


class TestSessionResolver:
    """ArvelModel.query() uses the session resolver when no session is passed."""

    def test_query_without_session_raises_when_no_resolver(self) -> None:
        ArvelModel.clear_session_resolver()
        with pytest.raises(RuntimeError, match="No session provided"):
            User.query()

    async def test_query_without_session_uses_resolver(self, db_session) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        try:
            qb = User.query()
            users = await qb.order_by(User.id).limit(10).all()
            assert isinstance(users, list)
        finally:
            ArvelModel.clear_session_resolver()

    async def test_query_with_explicit_session_ignores_resolver(self, db_session) -> None:
        called = False

        def bad_resolver():
            nonlocal called
            called = True
            return db_session

        ArvelModel.set_session_resolver(bad_resolver)
        try:
            qb = User.query(db_session)
            await qb.order_by(User.id).limit(10).all()
            assert not called, "Resolver should not be called when session is passed explicitly"
        finally:
            ArvelModel.clear_session_resolver()

    def test_clear_session_resolver(self) -> None:
        ArvelModel.set_session_resolver(lambda: None)  # type: ignore[arg-type,ty:invalid-argument-type]
        ArvelModel.clear_session_resolver()
        assert ArvelModel._session_resolver is None


class TestModelCreate:
    """User.create({...}) — Laravel-style static creation."""

    async def test_create_returns_model_with_id(self, db_session) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        try:
            user = await User.create({"name": "Alice", "email": "alice@model.com"})
            assert user.id is not None
            assert user.name == "Alice"
            assert user.email == "alice@model.com"
        finally:
            ArvelModel.clear_session_resolver()

    async def test_create_with_explicit_session(self, db_session) -> None:
        user = await User.create({"name": "Bob", "email": "bob@model.com"}, session=db_session)
        assert user.id is not None
        assert user.name == "Bob"

    async def test_create_respects_mass_assignment(self, db_session) -> None:
        from tests._fixtures.models import FillableUser

        ArvelModel.set_session_resolver(lambda: db_session)
        try:
            user = await FillableUser.create(
                {"name": "Eve", "email": "eve@model.com", "is_admin": True}
            )
            assert user.name == "Eve"
            assert user.is_admin is not True  # is_admin is not fillable
        finally:
            ArvelModel.clear_session_resolver()


class TestModelFind:
    """User.find(id) — Laravel-style static find."""

    async def test_find_existing_record(self, db_session) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        try:
            created = await User.create({"name": "Charlie", "email": "charlie@find.com"})
            found = await User.find(created.id)
            assert found.id == created.id
            assert found.name == "Charlie"
        finally:
            ArvelModel.clear_session_resolver()

    async def test_find_nonexistent_raises(self, db_session) -> None:
        from arvel.data.exceptions import NotFoundError

        ArvelModel.set_session_resolver(lambda: db_session)
        try:
            with pytest.raises(NotFoundError, match="User"):
                await User.find(999999)
        finally:
            ArvelModel.clear_session_resolver()

    async def test_find_or_none_returns_none(self, db_session) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        try:
            result = await User.find_or_none(999999)
            assert result is None
        finally:
            ArvelModel.clear_session_resolver()


class TestModelAll:
    """User.all() — Laravel-style static all."""

    async def test_all_returns_list(self, db_session) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        try:
            await User.create({"name": "D1", "email": "d1@all.com"})
            await User.create({"name": "D2", "email": "d2@all.com"})
            users = await User.all()
            assert len(users) >= 2
            assert all(isinstance(u, User) for u in users)
        finally:
            ArvelModel.clear_session_resolver()


class TestModelUpdate:
    """user.update({...}) — Laravel-style instance update."""

    async def test_update_changes_fields(self, db_session) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        try:
            user = await User.create({"name": "Before", "email": "update@model.com"})
            await user.update({"name": "After"})
            assert user.name == "After"
        finally:
            ArvelModel.clear_session_resolver()

    async def test_update_with_explicit_session(self, db_session) -> None:
        user = await User.create({"name": "Orig", "email": "orig@model.com"}, session=db_session)
        await user.update({"name": "Changed"}, session=db_session)
        assert user.name == "Changed"


class TestModelSave:
    """user.save() — Laravel-style instance save."""

    async def test_save_persists_attribute_changes(self, db_session) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        try:
            user = await User.create({"name": "SaveMe", "email": "save@model.com"})
            user.name = "Saved"
            await user.save()
            found = await User.find(user.id)
            assert found.name == "Saved"
        finally:
            ArvelModel.clear_session_resolver()


class TestModelDelete:
    """user.delete() — Laravel-style instance delete."""

    async def test_delete_removes_record(self, db_session) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        try:
            user = await User.create({"name": "Gone", "email": "gone@model.com"})
            user_id = user.id
            await user.delete()
            result = await User.find_or_none(user_id)
            assert result is None
        finally:
            ArvelModel.clear_session_resolver()


# ──── Epic 013: Observer Dispatch on Model CRUD ────


class _TrackingObserver(ModelObserver[User]):
    """Records which events fired and their order."""

    def __init__(self, *, abort_event: str | None = None) -> None:
        self.events: list[str] = []
        self._abort_event = abort_event

    async def saving(self, instance: User) -> bool:
        self.events.append("saving")
        return self._abort_event != "saving"

    async def saved(self, instance: User) -> None:
        self.events.append("saved")

    async def creating(self, instance: User) -> bool:
        self.events.append("creating")
        return self._abort_event != "creating"

    async def created(self, instance: User) -> None:
        self.events.append("created")

    async def updating(self, instance: User) -> bool:
        self.events.append("updating")
        return self._abort_event != "updating"

    async def updated(self, instance: User) -> None:
        self.events.append("updated")

    async def deleting(self, instance: User) -> bool:
        self.events.append("deleting")
        return self._abort_event != "deleting"

    async def deleted(self, instance: User) -> None:
        self.events.append("deleted")


@pytest.fixture
def _resolver_cleanup():
    """Cleanup session and observer resolvers after each test."""
    yield
    ArvelModel.clear_session_resolver()
    ArvelModel.clear_observer_registry()


class TestModelCreateObservers:
    """Model.create() fires saving → creating → created → saved."""

    async def test_create_fires_events_in_order(self, db_session, _resolver_cleanup) -> None:
        from arvel.data.observer import ObserverRegistry

        registry = ObserverRegistry()
        tracker = _TrackingObserver()
        registry.register(User, tracker)

        ArvelModel.set_session_resolver(lambda: db_session)
        ArvelModel.set_observer_registry(lambda: registry)

        await User.create({"name": "Obs", "email": "obs-create@test.com"})
        assert tracker.events == ["saving", "creating", "created", "saved"]

    async def test_create_aborted_by_saving(self, db_session, _resolver_cleanup) -> None:
        from arvel.data.exceptions import CreationAbortedError
        from arvel.data.observer import ObserverRegistry

        registry = ObserverRegistry()
        tracker = _TrackingObserver(abort_event="saving")
        registry.register(User, tracker)

        ArvelModel.set_session_resolver(lambda: db_session)
        ArvelModel.set_observer_registry(lambda: registry)

        with pytest.raises(CreationAbortedError):
            await User.create({"name": "Blocked", "email": "blocked-s@test.com"})
        assert tracker.events == ["saving"]

    async def test_create_aborted_by_creating(self, db_session, _resolver_cleanup) -> None:
        from arvel.data.exceptions import CreationAbortedError
        from arvel.data.observer import ObserverRegistry

        registry = ObserverRegistry()
        tracker = _TrackingObserver(abort_event="creating")
        registry.register(User, tracker)

        ArvelModel.set_session_resolver(lambda: db_session)
        ArvelModel.set_observer_registry(lambda: registry)

        with pytest.raises(CreationAbortedError):
            await User.create({"name": "Blocked", "email": "blocked-c@test.com"})
        assert tracker.events == ["saving", "creating"]

    async def test_create_no_observer_works(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await User.create({"name": "NoObs", "email": "noobs-create@test.com"})
        assert user.id is not None


class TestModelUpdateObservers:
    """model.update() fires saving → updating → updated → saved."""

    async def test_update_fires_events_in_order(self, db_session, _resolver_cleanup) -> None:
        from arvel.data.observer import ObserverRegistry

        registry = ObserverRegistry()
        tracker = _TrackingObserver()
        registry.register(User, tracker)

        ArvelModel.set_session_resolver(lambda: db_session)
        ArvelModel.set_observer_registry(lambda: registry)

        user = await User.create({"name": "Pre", "email": "obs-update@test.com"})
        tracker.events.clear()

        await user.update({"name": "Post"})
        assert tracker.events == ["saving", "updating", "updated", "saved"]

    async def test_update_aborted_by_updating(self, db_session, _resolver_cleanup) -> None:
        from arvel.data.exceptions import UpdateAbortedError
        from arvel.data.observer import ObserverRegistry

        registry = ObserverRegistry()
        ArvelModel.set_session_resolver(lambda: db_session)
        ArvelModel.set_observer_registry(lambda: registry)

        user = await User.create({"name": "Pre", "email": "obs-upd-abort@test.com"})

        tracker = _TrackingObserver(abort_event="updating")
        registry.register(User, tracker)

        with pytest.raises(UpdateAbortedError):
            await user.update({"name": "Blocked"})
        assert "updating" in tracker.events
        assert "updated" not in tracker.events


class TestModelSaveObservers:
    """model.save() detects new vs existing and fires appropriate events."""

    async def test_save_new_fires_creating_events(self, db_session, _resolver_cleanup) -> None:
        from arvel.data.observer import ObserverRegistry

        registry = ObserverRegistry()
        tracker = _TrackingObserver()
        registry.register(User, tracker)

        ArvelModel.set_session_resolver(lambda: db_session)
        ArvelModel.set_observer_registry(lambda: registry)

        user = User(name="NewSave", email="new-save@test.com")
        await user.save()
        assert "creating" in tracker.events
        assert "created" in tracker.events
        assert "updating" not in tracker.events

    async def test_save_existing_fires_updating_events(self, db_session, _resolver_cleanup) -> None:
        from arvel.data.observer import ObserverRegistry

        registry = ObserverRegistry()
        tracker = _TrackingObserver()
        registry.register(User, tracker)

        ArvelModel.set_session_resolver(lambda: db_session)
        ArvelModel.set_observer_registry(lambda: registry)

        user = await User.create({"name": "Existing", "email": "exist-save@test.com"})
        tracker.events.clear()

        user.name = "Updated"
        await user.save()
        assert "updating" in tracker.events
        assert "updated" in tracker.events
        assert "creating" not in tracker.events


class TestModelDeleteObservers:
    """model.delete() fires deleting → deleted."""

    async def test_delete_fires_events_in_order(self, db_session, _resolver_cleanup) -> None:
        from arvel.data.observer import ObserverRegistry

        registry = ObserverRegistry()
        tracker = _TrackingObserver()
        registry.register(User, tracker)

        ArvelModel.set_session_resolver(lambda: db_session)
        ArvelModel.set_observer_registry(lambda: registry)

        user = await User.create({"name": "Del", "email": "obs-del@test.com"})
        tracker.events.clear()

        await user.delete()
        assert tracker.events == ["deleting", "deleted"]

    async def test_delete_aborted_by_deleting(self, db_session, _resolver_cleanup) -> None:
        from arvel.data.exceptions import DeletionAbortedError
        from arvel.data.observer import ObserverRegistry

        registry = ObserverRegistry()
        ArvelModel.set_session_resolver(lambda: db_session)
        ArvelModel.set_observer_registry(lambda: registry)

        user = await User.create({"name": "NoDel", "email": "obs-nodel@test.com"})

        tracker = _TrackingObserver(abort_event="deleting")
        registry.register(User, tracker)

        with pytest.raises(DeletionAbortedError):
            await user.delete()
        assert tracker.events == ["deleting"]


# ──── Epic 014: Convenience Query Methods ────


class TestModelWhere:
    """User.where(...) shortcut."""

    async def test_where_returns_query_builder(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        qb = User.where(User.active == True)  # noqa: E712
        assert hasattr(qb, "all")
        assert hasattr(qb, "first")


class TestModelFirst:
    """User.first() shortcut."""

    async def test_first_returns_model_or_none(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        await User.create({"name": "First", "email": "first@conv.com"})
        result = await User.first()
        assert result is None or isinstance(result, User)


class TestModelCount:
    """User.count() shortcut."""

    async def test_count_returns_int(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        await User.create({"name": "Count1", "email": "count1@conv.com"})
        c = await User.count()
        assert isinstance(c, int)
        assert c >= 1


class TestModelFill:
    """user.fill(data) mass-assigns without saving."""

    async def test_fill_sets_attributes(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await User.create({"name": "FillMe", "email": "fill@conv.com"})
        result = user.fill({"name": "Filled"})
        assert user.name == "Filled"
        assert result is user

    async def test_fill_respects_mass_assignment(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await FillableUser.create({"name": "FA", "email": "fa-fill@conv.com"})
        user.fill({"name": "Changed", "is_admin": True})
        assert user.name == "Changed"
        assert user.is_admin is not True


class TestModelFindMany:
    """User.find_many([ids]) returns matching records."""

    async def test_find_many_returns_found_records(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        u1 = await User.create({"name": "FM1", "email": "fm1@conv.com"})
        u2 = await User.create({"name": "FM2", "email": "fm2@conv.com"})
        found = await User.find_many([u1.id, u2.id])
        ids = {u.id for u in found}
        assert u1.id in ids
        assert u2.id in ids

    async def test_find_many_skips_missing(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        u1 = await User.create({"name": "FM3", "email": "fm3@conv.com"})
        found = await User.find_many([u1.id, 999888])
        assert len(found) == 1

    async def test_find_many_empty_list(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        found = await User.find_many([])
        assert found == []


class TestModelDestroy:
    """User.destroy(ids) deletes by PK."""

    async def test_destroy_deletes_records(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        u1 = await User.create({"name": "D1", "email": "d1@destroy.com"})
        u2 = await User.create({"name": "D2", "email": "d2@destroy.com"})
        count = await User.destroy([u1.id, u2.id])
        assert count == 2
        assert await User.find_or_none(u1.id) is None
        assert await User.find_or_none(u2.id) is None

    async def test_destroy_single_id(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        u = await User.create({"name": "D3", "email": "d3@destroy.com"})
        count = await User.destroy(u.id)
        assert count == 1


class TestFirstOrCreate:
    """User.first_or_create() — find or create."""

    async def test_creates_when_not_found(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await User.first_or_create(
            {"email": "foc-new@test.com"},
            {"name": "FOC"},
        )
        assert user.id is not None
        assert user.email == "foc-new@test.com"
        assert user.name == "FOC"

    async def test_finds_existing(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        existing = await User.create({"name": "Exist", "email": "foc-exist@test.com"})
        found = await User.first_or_create(
            {"email": "foc-exist@test.com"},
            {"name": "ShouldNotUse"},
        )
        assert found.id == existing.id
        assert found.name == "Exist"


class TestFirstOrNew:
    """User.first_or_new() — build unsaved instance."""

    def test_returns_unsaved_instance(self) -> None:
        instance = User.first_or_new(
            {"email": "fon@test.com"},
            {"name": "FON"},
        )
        assert instance.email == "fon@test.com"
        assert instance.name == "FON"
        assert instance.id is None


class TestUpdateOrCreate:
    """User.update_or_create() — upsert."""

    async def test_creates_when_not_found(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await User.update_or_create(
            {"email": "uoc-new@test.com"},
            {"name": "UOC"},
        )
        assert user.id is not None
        assert user.name == "UOC"

    async def test_updates_when_found(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        existing = await User.create({"name": "Old", "email": "uoc-exist@test.com"})
        updated = await User.update_or_create(
            {"email": "uoc-exist@test.com"},
            {"name": "New"},
        )
        assert updated.id == existing.id
        assert updated.name == "New"


class TestQueryBuilderAggregates:
    """QueryBuilder.max/min/sum/avg."""

    async def test_max_returns_correct_value(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        await User.create({"name": "A10", "email": "a10@agg.com", "age": 10})
        await User.create({"name": "A20", "email": "a20@agg.com", "age": 20})
        result = await User.query().max(User.age)
        assert result >= 20

    async def test_min_returns_correct_value(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        await User.create({"name": "M10", "email": "m10@agg.com", "age": 5})
        result = await User.query().min(User.age)
        assert result is not None
        assert result <= 5

    async def test_sum_returns_correct_value(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        await User.create({"name": "S1", "email": "s1@agg.com", "age": 10})
        await User.create({"name": "S2", "email": "s2@agg.com", "age": 15})
        result = await User.query().sum(User.age)
        assert result is not None
        assert result >= 25

    async def test_avg_returns_correct_value(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        await User.create({"name": "Av1", "email": "av1@agg.com", "age": 10})
        await User.create({"name": "Av2", "email": "av2@agg.com", "age": 30})
        result = await User.query().avg(User.age)
        assert result is not None


# ──── Epic 015: Transparent Casting & Mutators ────


class TestTransparentCastRead:
    """__getattribute__ applies casters on read."""

    async def test_json_cast_returns_dict(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await CastUser.create(
            {
                "name": "Cast1",
                "email": "cast1@test.com",
                "settings": '{"theme": "dark"}',
            }
        )
        assert isinstance(user.settings, dict)
        assert user.settings["theme"] == "dark"

    async def test_bool_cast_returns_bool(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await CastUser.create(
            {
                "name": "Cast2",
                "email": "cast2@test.com",
                "is_verified": 1,
            }
        )
        assert user.is_verified is True

    async def test_int_cast_returns_int(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await CastUser.create(
            {
                "name": "Cast3",
                "email": "cast3@test.com",
                "score": "42",
            }
        )
        assert user.score == 42
        assert isinstance(user.score, int)

    async def test_none_values_pass_through(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await CastUser.create(
            {
                "name": "Cast4",
                "email": "cast4@test.com",
            }
        )
        assert user.settings is None
        assert user.is_verified is None


class TestTransparentCastWrite:
    """__setattr__ applies casters on write."""

    async def test_json_cast_on_set(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await CastUser.create(
            {
                "name": "CastW1",
                "email": "castw1@test.com",
            }
        )
        user.settings = {"layout": "grid"}  # ty: ignore[invalid-assignment]  # caster descriptor accepts dict at runtime
        assert isinstance(object.__getattribute__(user, "settings"), str)

    async def test_bool_cast_on_set(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await CastUser.create(
            {
                "name": "CastW2",
                "email": "castw2@test.com",
            }
        )
        user.is_verified = True
        assert user.is_verified is True


class TestCastInModelDump:
    """model_dump() returns cast-transformed values."""

    async def test_dump_includes_cast_values(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await CastUser.create(
            {
                "name": "CastD",
                "email": "castd@test.com",
                "settings": '{"k": "v"}',
                "is_verified": 1,
                "score": "99",
            }
        )
        dump = user.model_dump()
        assert dump["settings"] == {"k": "v"}
        assert dump["is_verified"] is True
        assert dump["score"] == 99


class TestMutatorIntegration:
    """@mutator transforms values on __setattr__."""

    async def test_mutator_runs_on_setattr(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await MutatorUser.create(
            {
                "name": "  alice smith  ",
                "email": "mut1@test.com",
            }
        )
        assert user.name == "Alice Smith"

    async def test_mutator_runs_on_direct_set(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await MutatorUser.create(
            {
                "name": "bob",
                "email": "mut2@test.com",
            }
        )
        user.name = "  charlie brown  "
        assert user.name == "Charlie Brown"


# ──── Epic 016: Serialization Control ────


class TestHidden:
    """__hidden__ excludes fields from model_dump()."""

    async def test_hidden_fields_excluded(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await HiddenUser.create(
            {
                "name": "H1",
                "email": "h1@test.com",
                "password": "secret123",
                "secret_token": "tok-abc",
            }
        )
        dump = user.model_dump()
        assert "name" in dump
        assert "email" in dump
        assert "password" not in dump
        assert "secret_token" not in dump

    async def test_hidden_still_accessible_on_instance(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await HiddenUser.create(
            {
                "name": "H2",
                "email": "h2@test.com",
                "password": "secret456",
            }
        )
        assert user.password == "secret456"


class TestVisible:
    """__visible__ whitelists fields in model_dump()."""

    async def test_only_visible_fields_returned(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await VisibleUser.create(
            {
                "name": "V1",
                "email": "v1@test.com",
                "password": "hidden",
                "internal_notes": "private",
            }
        )
        dump = user.model_dump()
        assert set(dump.keys()) == {"id", "name", "email"}


class TestAppends:
    """__appends__ includes accessor values in model_dump()."""

    async def test_appended_accessor_included(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await AppendedUser.create(
            {
                "first_name": "Jane",
                "last_name": "Doe",
                "email": "app1@test.com",
            }
        )
        dump = user.model_dump()
        assert dump["display_name"] == "Jane Doe"


class TestMakeHidden:
    """Instance-level make_hidden() / make_visible()."""

    async def test_make_hidden_excludes_fields(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await User.create({"name": "MH1", "email": "mh1@test.com"})
        user.make_hidden("email", "age")
        dump = user.model_dump()
        assert "email" not in dump
        assert "age" not in dump
        assert "name" in dump

    async def test_make_visible_overrides_class_hidden(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await HiddenUser.create(
            {
                "name": "MV1",
                "email": "mv1@test.com",
                "password": "reveal",
            }
        )
        user.make_visible("password")
        dump = user.model_dump()
        assert dump["password"] == "reveal"
        assert "secret_token" not in dump

    async def test_make_hidden_chains(self, db_session, _resolver_cleanup) -> None:
        ArvelModel.set_session_resolver(lambda: db_session)
        user = await User.create({"name": "MH2", "email": "mh2@test.com"})
        result = user.make_hidden("email")
        assert result is user


class TestModelJson:
    """model_json() returns a JSON string."""

    async def test_model_json_returns_valid_json(self, db_session, _resolver_cleanup) -> None:
        import json as _json

        ArvelModel.set_session_resolver(lambda: db_session)
        user = await User.create({"name": "Json1", "email": "json1@test.com"})
        result = user.model_json()
        assert isinstance(result, str)
        parsed = _json.loads(result)
        assert parsed["name"] == "Json1"

    async def test_model_json_respects_hidden(self, db_session, _resolver_cleanup) -> None:
        import json as _json

        ArvelModel.set_session_resolver(lambda: db_session)
        user = await HiddenUser.create(
            {
                "name": "Json2",
                "email": "json2@test.com",
                "password": "nope",
            }
        )
        result = user.model_json()
        parsed = _json.loads(result)
        assert "password" not in parsed
