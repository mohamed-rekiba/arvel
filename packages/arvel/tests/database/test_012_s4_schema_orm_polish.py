"""Schema DSL extensions and ORM polish."""

from __future__ import annotations

import pytest
from arvel.database import Model, id_, integer, string
from arvel.database.schema import Blueprint, Schema
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

# ───  Schema column modification and introspection ─────────────────


async def test_schema_has_table_true(engine: AsyncEngine, session: AsyncSession) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)
    exists = await Schema.has_table(engine, "sqlite_master")
    assert exists is True


async def test_schema_has_table_false(engine: AsyncEngine, session: AsyncSession) -> None:
    exists = await Schema.has_table(engine, "nonexistent_table_xyz")
    assert exists is False


async def test_schema_has_column(engine: AsyncEngine, session: AsyncSession) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: c.execute(
                __import__("sqlalchemy").text(
                    "CREATE TABLE IF NOT EXISTS col_test (id INTEGER PRIMARY KEY, name TEXT)"
                )
            )
        )
    assert await Schema.has_column(engine, "col_test", "name") is True
    assert await Schema.has_column(engine, "col_test", "nonexistent") is False


async def test_schema_get_columns(engine: AsyncEngine, session: AsyncSession) -> None:
    create_sql = (
        "CREATE TABLE IF NOT EXISTS getcols_test (id INTEGER PRIMARY KEY, title TEXT NOT NULL)"
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: c.execute(__import__("sqlalchemy").text(create_sql)))
    cols = await Schema.get_columns(engine, "getcols_test")
    names = [c["name"] for c in cols]
    assert "id" in names
    assert "title" in names


# ───  New column types ─────────────────────────────────────────────


def test_blueprint_uuid_method() -> None:
    bp = Blueprint("test")
    col = bp.uuid("uid")
    assert col is not None


def test_blueprint_ulid_method() -> None:
    bp = Blueprint("test")
    col = bp.ulid("ulid_col")
    assert col is not None


def test_blueprint_enum_method() -> None:
    bp = Blueprint("test")
    col = bp.enum("status", ["active", "inactive", "pending"])
    assert col is not None


def test_blueprint_tiny_integer_method() -> None:
    bp = Blueprint("test")
    col = bp.tiny_integer("flag")
    assert col is not None


def test_blueprint_ip_address_method() -> None:
    bp = Blueprint("test")
    col = bp.ip_address("ip")
    assert col is not None


def test_blueprint_geometry_method() -> None:
    bp = Blueprint("test")
    col = bp.geometry("location")
    assert col is not None


# ───  Column modifiers and drop helpers ────────────────────────────


def test_blueprint_drop_timestamps() -> None:
    bp = Blueprint("test")
    bp.drop_timestamps()  # Should not raise


def test_blueprint_drop_soft_deletes() -> None:
    bp = Blueprint("test")
    bp.drop_soft_deletes()  # Should not raise


def test_blueprint_drop_morphs() -> None:
    bp = Blueprint("test")
    bp.drop_morphs("taggable")  # Should not raise


def test_column_comment_modifier() -> None:
    bp = Blueprint("test")
    col = bp.string("bio").comment("User biography")
    assert col is not None


def test_column_after_modifier() -> None:
    bp = Blueprint("test")
    col = bp.string("code").after("email")
    assert col is not None


# ───  FK cascade shorthands ───────────────────────────────────────


def test_cascade_on_delete_shorthand() -> None:
    bp = Blueprint("test")
    col = bp.foreign_id("user_id").constrained().cascade_on_delete()
    assert col is not None


def test_null_on_delete_shorthand() -> None:
    bp = Blueprint("test")
    col = bp.foreign_id("parent_id").constrained().null_on_delete()
    assert col is not None


def test_restrict_on_delete_shorthand() -> None:
    bp = Blueprint("test")
    col = bp.foreign_id("ref_id").constrained().restrict_on_delete()
    assert col is not None


# ───  Mass assignment protection ──────────────────────────────────


async def test_fillable_blocks_non_listed_field(engine: AsyncEngine, session: AsyncSession) -> None:
    from arvel.database.exceptions import MassAssignmentError

    class ProtectedPost(Model):
        __tablename__ = "protected_posts"
        __fillable__ = ["title"]
        id: int = id_()
        title: str = string(200)
        slug: str | None = string(200, nullable=True, default=None)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    with pytest.raises(MassAssignmentError):
        await ProtectedPost.create(title="ok", slug="not-allowed")


async def test_fillable_allows_listed_field(engine: AsyncEngine, session: AsyncSession) -> None:
    class AllowedPost(Model):
        __tablename__ = "allowed_posts"
        __fillable__ = ["title"]
        id: int = id_()
        title: str = string(200)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    post = await AllowedPost.create(title="Safe")
    assert post.title == "Safe"


async def test_guarded_blocks_guarded_field(engine: AsyncEngine, session: AsyncSession) -> None:
    from arvel.database.exceptions import MassAssignmentError

    class GuardedModel(Model):
        __tablename__ = "guarded_model"
        __guarded__ = ["admin_only"]
        id: int = id_()
        name: str = string(80)
        admin_only: str | None = string(80, nullable=True, default=None)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    with pytest.raises(MassAssignmentError):
        await GuardedModel.create(name="ok", admin_only="secret")


async def test_guarded_wildcard_blocks_all_mass_assignment(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    from arvel.database.exceptions import MassAssignmentError

    class GuardAllModel(Model):
        __tablename__ = "guard_all_model"
        __guarded__ = ["*"]
        id: int = id_()
        name: str = string(80)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    with pytest.raises(MassAssignmentError):
        await GuardAllModel.create(name="blocked")


async def test_no_protection_when_neither_set(engine: AsyncEngine, session: AsyncSession) -> None:
    """Without __fillable__ or __guarded__, all fields are allowed."""

    class OpenModel(Model):
        __tablename__ = "open_model"
        id: int = id_()
        name: str = string(80)
        note: str | None = string(200, nullable=True, default=None)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    obj = await OpenModel.create(name="all_ok", note="anything")
    assert obj.note == "anything"


# ───  Serialization control ───────────────────────────────────────


async def test_hidden_fields_excluded_from_dict(engine: AsyncEngine, session: AsyncSession) -> None:
    class SecureUser(Model):
        __tablename__ = "secure_users"
        __hidden__ = ["password"]
        id: int = id_()
        name: str = string(80)
        password: str = string(200)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    u = await SecureUser.create(name="Alice", password="hash123")
    d = u.to_dict()
    assert "password" not in d
    assert "name" in d


async def test_visible_limits_dict_to_listed_fields(
    engine: AsyncEngine, session: AsyncSession
) -> None:
    class VisibleUser(Model):
        __tablename__ = "visible_users"
        __visible__ = ["id", "name"]
        id: int = id_()
        name: str = string(80)
        email: str = string(200)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    u = await VisibleUser.create(name="Bob", email="bob@example.com")
    d = u.to_dict()
    assert set(d.keys()) <= {"id", "name"}
    assert "email" not in d


async def test_make_hidden_per_instance(engine: AsyncEngine, session: AsyncSession) -> None:
    class PlainUser(Model):
        __tablename__ = "plain_users"
        id: int = id_()
        name: str = string(80)
        score: int = integer(default=0)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    u = await PlainUser.create(name="Charlie", score=100)
    u.make_hidden("score")
    d = u.to_dict()
    assert "score" not in d
    # Must not mutate the class
    assert "score" not in (PlainUser.__hidden__ or [])


# ───  Touch and replicate ─────────────────────────────────────────


async def test_touch_updates_updated_at(engine: AsyncEngine, session: AsyncSession) -> None:
    from arvel.database.model import Timestamps

    class TimedItem(Model, Timestamps):
        __tablename__ = "timed_items"
        id: int = id_()
        name: str = string(80)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    item = await TimedItem.create(name="touchme")
    original_ts = item.updated_at

    import asyncio

    await asyncio.sleep(0.01)
    await item.touch()

    assert item.updated_at > original_ts


async def test_replicate_creates_unsaved_copy(engine: AsyncEngine, session: AsyncSession) -> None:
    class ReplicaModel(Model):
        __tablename__ = "replica_models"
        id: int = id_()
        name: str = string(80)
        note: str | None = string(200, nullable=True, default=None)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    original = await ReplicaModel.create(name="orig", note="keepme")
    clone = await original.replicate()

    assert clone.id is None  # unsaved
    assert clone.name == "orig"
    assert clone.note == "keepme"


async def test_replicate_except_excludes_fields(engine: AsyncEngine, session: AsyncSession) -> None:
    class ExceptModel(Model):
        __tablename__ = "except_models"
        id: int = id_()
        name: str = string(80)
        slug: str | None = string(80, nullable=True, default=None)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    original = await ExceptModel.create(name="source", slug="src-slug")
    clone = await original.replicate(except_=["slug"])

    assert clone.name == "source"
    assert clone.slug is None


# ───  Complete model events ───────────────────────────────────────


async def test_retrieved_event_fires(engine: AsyncEngine, session: AsyncSession) -> None:
    class TrackedModel(Model):
        __tablename__ = "tracked_models"
        id: int = id_()
        name: str = string(80)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    fired: list[str] = []

    class TrackedObserver:
        async def retrieved(self, instance: TrackedModel) -> None:
            fired.append("retrieved")

    TrackedModel.observe(TrackedObserver())

    item = await TrackedModel.create(name="observe_me")
    await TrackedModel.find(item.id)

    assert "retrieved" in fired


async def test_saving_and_saved_events_fire(engine: AsyncEngine, session: AsyncSession) -> None:
    class SavingModel(Model):
        __tablename__ = "saving_models"
        id: int = id_()
        name: str = string(80)

    async with engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    fired: list[str] = []

    class SavingObserver:
        async def saving(self, instance: SavingModel) -> None:
            fired.append("saving")

        async def saved(self, instance: SavingModel) -> None:
            fired.append("saved")

    SavingModel.observe(SavingObserver())
    await SavingModel.create(name="fire_events")
    assert "saving" in fired
    assert "saved" in fired
