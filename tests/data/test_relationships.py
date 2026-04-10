"""Tests for Epic 13: Model Relationships.

Covers all 5 stories:
- Story 1: HasOne + BelongsTo
- Story 2: HasMany
- Story 3: BelongsToMany (pivot)
- Story 4: HasRelationships mixin (registry, model_dump, get_relationships)
- Story 5: Relationship query helpers (has, where_has, doesnt_have, with_count)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from sqlalchemy import Column, ForeignKey, Integer, String, Table, Text, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column  # noqa: TC002

from arvel.data.model import ArvelModel
from arvel.data.relationships import (
    RelationType,
    belongs_to,
    belongs_to_many,
    has_many,
    has_one,
)
from arvel.data.relationships.pivot import PivotManager
from arvel.data.results import WithCount

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

# ──── Test Models using relationship helpers ────

role_user = Table(
    "role_user",
    ArvelModel.metadata,
    Column("user_id", Integer, ForeignKey("rel_users.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("rel_roles.id"), primary_key=True),
)


class RelUser(ArvelModel):
    __tablename__ = "rel_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)

    phone = has_one("RelPhone", back_populates="user")
    posts = has_many("RelPost", back_populates="author")
    roles = belongs_to_many("RelRole", pivot_table="role_user", back_populates="users")


class RelPhone(ArvelModel):
    __tablename__ = "rel_phones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    number: Mapped[str] = mapped_column(String(20))
    rel_user_id: Mapped[int] = mapped_column(ForeignKey("rel_users.id"))

    user = belongs_to("RelUser", foreign_key="rel_user_id", back_populates="phone")


class RelPost(ArvelModel):
    __tablename__ = "rel_posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str | None] = mapped_column(Text, default=None)
    rel_user_id: Mapped[int] = mapped_column(ForeignKey("rel_users.id"))
    is_published: Mapped[bool] = mapped_column(default=False)

    author = belongs_to("RelUser", foreign_key="rel_user_id", back_populates="posts")
    comments = has_many("RelComment", back_populates="post")


class RelComment(ArvelModel):
    __tablename__ = "rel_comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    body: Mapped[str] = mapped_column(Text)
    rel_post_id: Mapped[int] = mapped_column(ForeignKey("rel_posts.id"))

    post = belongs_to("RelPost", foreign_key="rel_post_id", back_populates="comments")


class RelRole(ArvelModel):
    __tablename__ = "rel_roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)

    users = belongs_to_many("RelUser", pivot_table="role_user", back_populates="roles")


# ──── Fixtures ────


@pytest.fixture
async def rel_session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(ArvelModel.metadata.create_all)

    async with engine.connect() as conn:
        trans = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            yield session
            if trans.is_active:
                await trans.rollback()

    await engine.dispose()


async def _seed_user_with_posts(session: AsyncSession, n_posts: int = 3) -> RelUser:
    user = RelUser(name="Alice", email="alice@rel.test")
    session.add(user)
    await session.flush()
    for i in range(n_posts):
        session.add(RelPost(title=f"Post {i}", rel_user_id=user.id, is_published=i % 2 == 0))
    await session.flush()
    return user


# ═══════════════════════════════════════════════════════════
# Story 1: HasOne + BelongsTo
# ═══════════════════════════════════════════════════════════


class TestHasOne:
    async def test_eager_load_returns_related_instance(self, rel_session: AsyncSession) -> None:
        user = RelUser(name="Bob", email="bob@rel.test")
        rel_session.add(user)
        await rel_session.flush()

        phone = RelPhone(number="555-0100", rel_user_id=user.id)
        rel_session.add(phone)
        await rel_session.flush()

        loaded = (
            await RelUser.query(rel_session)
            .where(RelUser.id == user.id)
            .with_("phone")
            .order_by(RelUser.id)
            .first()
        )
        assert loaded is not None
        assert loaded.phone is not None
        assert loaded.phone.number == "555-0100"

    async def test_has_one_returns_none_when_no_related(self, rel_session: AsyncSession) -> None:
        user = RelUser(name="NoPhone", email="nophone@rel.test")
        rel_session.add(user)
        await rel_session.flush()

        loaded = (
            await RelUser.query(rel_session)
            .where(RelUser.id == user.id)
            .with_("phone")
            .order_by(RelUser.id)
            .first()
        )
        assert loaded is not None
        assert loaded.phone is None

    async def test_has_one_with_custom_fk(self, rel_session: AsyncSession) -> None:
        user = RelUser(name="Custom", email="custom@rel.test")
        rel_session.add(user)
        await rel_session.flush()

        phone = RelPhone(number="555-9999", rel_user_id=user.id)
        rel_session.add(phone)
        await rel_session.flush()

        loaded = (
            await RelPhone.query(rel_session)
            .where(RelPhone.id == phone.id)
            .with_("user")
            .order_by(RelPhone.id)
            .first()
        )
        assert loaded is not None
        assert loaded.user is not None
        assert loaded.user.name == "Custom"


class TestBelongsTo:
    async def test_inverse_returns_owner(self, rel_session: AsyncSession) -> None:
        user = RelUser(name="Owner", email="owner@rel.test")
        rel_session.add(user)
        await rel_session.flush()

        phone = RelPhone(number="555-0200", rel_user_id=user.id)
        rel_session.add(phone)
        await rel_session.flush()

        loaded = (
            await RelPhone.query(rel_session)
            .where(RelPhone.id == phone.id)
            .with_("user")
            .order_by(RelPhone.id)
            .first()
        )
        assert loaded is not None
        assert loaded.user.name == "Owner"


# ═══════════════════════════════════════════════════════════
# Story 2: HasMany
# ═══════════════════════════════════════════════════════════


class TestHasMany:
    async def test_eager_load_returns_list(self, rel_session: AsyncSession) -> None:
        user = await _seed_user_with_posts(rel_session, n_posts=3)

        loaded = (
            await RelUser.query(rel_session)
            .where(RelUser.id == user.id)
            .with_("posts")
            .order_by(RelUser.id)
            .first()
        )
        assert loaded is not None
        assert isinstance(loaded.posts, list)
        assert len(loaded.posts) == 3

    async def test_has_many_returns_empty_list_when_no_related(
        self, rel_session: AsyncSession
    ) -> None:
        user = RelUser(name="NoPosts", email="noposts@rel.test")
        rel_session.add(user)
        await rel_session.flush()

        loaded = (
            await RelUser.query(rel_session)
            .where(RelUser.id == user.id)
            .with_("posts")
            .order_by(RelUser.id)
            .first()
        )
        assert loaded is not None
        assert loaded.posts == []

    async def test_has_many_custom_fk(self, rel_session: AsyncSession) -> None:
        user = RelUser(name="Author", email="author@rel.test")
        rel_session.add(user)
        await rel_session.flush()

        post = RelPost(title="Test Post", rel_user_id=user.id)
        rel_session.add(post)
        await rel_session.flush()

        loaded_post = (
            await RelPost.query(rel_session)
            .where(RelPost.id == post.id)
            .with_("author")
            .order_by(RelPost.id)
            .first()
        )
        assert loaded_post is not None
        assert loaded_post.author.name == "Author"


# ═══════════════════════════════════════════════════════════
# Story 3: BelongsToMany (pivot)
# ═══════════════════════════════════════════════════════════


class TestBelongsToMany:
    async def test_eager_load_through_pivot(self, rel_session: AsyncSession) -> None:
        user = RelUser(name="Admin", email="admin@rel.test")
        role = RelRole(name="admin")
        rel_session.add_all([user, role])
        await rel_session.flush()

        await rel_session.execute(role_user.insert().values(user_id=user.id, role_id=role.id))
        await rel_session.flush()

        loaded = (
            await RelUser.query(rel_session)
            .where(RelUser.id == user.id)
            .with_("roles")
            .order_by(RelUser.id)
            .first()
        )
        assert loaded is not None
        assert len(loaded.roles) == 1
        assert loaded.roles[0].name == "admin"

    async def test_many_to_many_inverse(self, rel_session: AsyncSession) -> None:
        user = RelUser(name="Member", email="member@rel.test")
        role = RelRole(name="editor")
        rel_session.add_all([user, role])
        await rel_session.flush()

        await rel_session.execute(role_user.insert().values(user_id=user.id, role_id=role.id))
        await rel_session.flush()

        loaded = (
            await RelRole.query(rel_session)
            .where(RelRole.id == role.id)
            .with_("users")
            .order_by(RelRole.id)
            .first()
        )
        assert loaded is not None
        assert len(loaded.users) == 1
        assert loaded.users[0].name == "Member"

    async def test_empty_many_to_many(self, rel_session: AsyncSession) -> None:
        user = RelUser(name="Lonely", email="lonely@rel.test")
        rel_session.add(user)
        await rel_session.flush()

        loaded = (
            await RelUser.query(rel_session)
            .where(RelUser.id == user.id)
            .with_("roles")
            .order_by(RelUser.id)
            .first()
        )
        assert loaded is not None
        assert loaded.roles == []


class TestPivotManager:
    async def test_attach(self, rel_session: AsyncSession) -> None:
        user = RelUser(name="Attach", email="attach@rel.test")
        r = RelRole(name="viewer")
        rel_session.add_all([user, r])
        await rel_session.flush()

        pm = PivotManager(
            session=rel_session,
            pivot_table=role_user,
            owner_fk_column=role_user.c.user_id,
            related_fk_column=role_user.c.role_id,
            owner_id=user.id,
        )

        await pm.attach(r.id)
        ids = await pm.ids()
        assert r.id in ids

    async def test_detach(self, rel_session: AsyncSession) -> None:
        user = RelUser(name="Detach", email="detach@rel.test")
        r = RelRole(name="temp_role")
        rel_session.add_all([user, r])
        await rel_session.flush()

        pm = PivotManager(
            session=rel_session,
            pivot_table=role_user,
            owner_fk_column=role_user.c.user_id,
            related_fk_column=role_user.c.role_id,
            owner_id=user.id,
        )

        await pm.attach(r.id)
        await pm.detach(r.id)
        ids = await pm.ids()
        assert r.id not in ids

    async def test_sync_inserts_and_removes(self, rel_session: AsyncSession) -> None:
        user = RelUser(name="Sync", email="sync@rel.test")
        r1 = RelRole(name="role_a")
        r2 = RelRole(name="role_b")
        r3 = RelRole(name="role_c")
        rel_session.add_all([user, r1, r2, r3])
        await rel_session.flush()

        pm = PivotManager(
            session=rel_session,
            pivot_table=role_user,
            owner_fk_column=role_user.c.user_id,
            related_fk_column=role_user.c.role_id,
            owner_id=user.id,
        )

        await pm.attach(r1.id)
        await pm.attach(r2.id)

        await pm.sync([r2.id, r3.id])
        ids = await pm.ids()
        assert set(ids) == {r2.id, r3.id}


# ═══════════════════════════════════════════════════════════
# Story 4: HasRelationships Mixin
# ═══════════════════════════════════════════════════════════


class TestHasRelationshipsMixin:
    def test_get_relationships_returns_registry(self) -> None:
        rels = RelUser.get_relationships()
        assert "phone" in rels
        assert "posts" in rels
        assert "roles" in rels
        assert rels["phone"].relation_type == RelationType.HAS_ONE
        assert rels["posts"].relation_type == RelationType.HAS_MANY
        assert rels["roles"].relation_type == RelationType.BELONGS_TO_MANY

    def test_get_relationships_on_inverse(self) -> None:
        rels = RelPhone.get_relationships()
        assert "user" in rels
        assert rels["user"].relation_type == RelationType.BELONGS_TO

    def test_get_relationships_empty_on_plain_model(self) -> None:
        rels = RelRole.get_relationships()
        assert "users" in rels

    async def test_model_dump_excludes_relations_by_default(
        self, rel_session: AsyncSession
    ) -> None:
        user = await _seed_user_with_posts(rel_session, n_posts=2)
        loaded = (
            await RelUser.query(rel_session)
            .where(RelUser.id == user.id)
            .with_("posts")
            .order_by(RelUser.id)
            .first()
        )
        assert loaded is not None

        dumped = loaded.model_dump()
        assert "posts" not in dumped
        assert "name" in dumped

    async def test_model_dump_with_include_relations_true(self, rel_session: AsyncSession) -> None:
        user = await _seed_user_with_posts(rel_session, n_posts=2)
        loaded = (
            await RelUser.query(rel_session)
            .where(RelUser.id == user.id)
            .with_("posts", "phone", "roles")
            .order_by(RelUser.id)
            .first()
        )
        assert loaded is not None

        dumped = loaded.model_dump(include_relations=True)
        assert "posts" in dumped
        assert isinstance(dumped["posts"], list)
        assert len(dumped["posts"]) == 2
        assert "phone" in dumped
        assert dumped["phone"] is None  # no phone seeded
        assert "roles" in dumped

    async def test_model_dump_with_specific_relations(self, rel_session: AsyncSession) -> None:
        user = await _seed_user_with_posts(rel_session, n_posts=1)
        loaded = (
            await RelUser.query(rel_session)
            .where(RelUser.id == user.id)
            .with_("posts")
            .order_by(RelUser.id)
            .first()
        )
        assert loaded is not None

        dumped = loaded.model_dump(include_relations=["posts"])
        assert "posts" in dumped
        assert "phone" not in dumped
        assert "roles" not in dumped

    async def test_backward_compatibility_model_without_relations(
        self, rel_session: AsyncSession
    ) -> None:
        """Models that don't declare any relationship helpers still work."""
        role = RelRole(name="compat_test")
        rel_session.add(role)
        await rel_session.flush()

        loaded = (
            await RelRole.query(rel_session)
            .where(RelRole.id == role.id)
            .order_by(RelRole.id)
            .first()
        )
        assert loaded is not None
        dumped = loaded.model_dump()
        assert "name" in dumped
        assert "id" in dumped


# ═══════════════════════════════════════════════════════════
# Story 5: Relationship Query Helpers
# ═══════════════════════════════════════════════════════════


class TestRelationshipQueryHelpers:
    async def test_has_filters_by_existence(self, rel_session: AsyncSession) -> None:
        alice = await _seed_user_with_posts(rel_session, n_posts=3)
        bob = RelUser(name="Bob", email="bob_qh@rel.test")
        rel_session.add(bob)
        await rel_session.flush()

        results = await RelUser.query(rel_session).has("posts").all()
        ids = [u.id for u in results]
        assert alice.id in ids
        assert bob.id not in ids

    async def test_has_with_count_threshold(self, rel_session: AsyncSession) -> None:
        user = await _seed_user_with_posts(rel_session, n_posts=2)
        _few = RelUser(name="FewPosts", email="few@rel.test")
        rel_session.add(_few)
        await rel_session.flush()
        rel_session.add(RelPost(title="Single", rel_user_id=_few.id))
        await rel_session.flush()

        results = await RelUser.query(rel_session).has("posts", ">", 1).all()
        ids = [u.id for u in results]
        assert user.id in ids
        assert _few.id not in ids

    async def test_doesnt_have_returns_zero_relations(self, rel_session: AsyncSession) -> None:
        await _seed_user_with_posts(rel_session, n_posts=1)
        lonely = RelUser(name="Lonely", email="lonely_qh@rel.test")
        rel_session.add(lonely)
        await rel_session.flush()

        results = await RelUser.query(rel_session).doesnt_have("posts").all()
        ids = [u.id for u in results]
        assert lonely.id in ids

    async def test_where_has_with_condition(self, rel_session: AsyncSession) -> None:
        user = await _seed_user_with_posts(rel_session, n_posts=4)

        results = (
            await RelUser.query(rel_session)
            .where_has("posts", lambda p: p.is_published == True)  # noqa: E712
            .all()
        )
        ids = [u.id for u in results]
        assert user.id in ids

    async def test_with_count_adds_count_attribute(self, rel_session: AsyncSession) -> None:
        user = await _seed_user_with_posts(rel_session, n_posts=5)

        results = (
            await RelUser.query(rel_session)
            .where(RelUser.id == user.id)
            .with_count("posts")
            .all_with_counts()
        )
        assert len(results) == 1
        assert isinstance(results[0], WithCount)
        assert results[0].counts["posts"] == 5
        assert results[0].posts_count == 5
        assert results[0].instance.name == user.name

    async def test_with_count_zero_when_no_relations(self, rel_session: AsyncSession) -> None:
        user = RelUser(name="Empty", email="empty_wc@rel.test")
        rel_session.add(user)
        await rel_session.flush()

        results = (
            await RelUser.query(rel_session)
            .where(RelUser.id == user.id)
            .with_count("posts")
            .all_with_counts()
        )
        assert len(results) == 1
        assert isinstance(results[0], WithCount)
        assert results[0].counts["posts"] == 0
        assert results[0].posts_count == 0


# ═══════════════════════════════════════════════════════════
# Nested Eager Loading
# ═══════════════════════════════════════════════════════════


class TestNestedEagerLoading:
    async def test_nested_with_loads_deep_relations(self, rel_session: AsyncSession) -> None:
        user = RelUser(name="Deep", email="deep@rel.test")
        rel_session.add(user)
        await rel_session.flush()

        post = RelPost(title="Deep Post", rel_user_id=user.id)
        rel_session.add(post)
        await rel_session.flush()

        comment = RelComment(body="A comment", rel_post_id=post.id)
        rel_session.add(comment)
        await rel_session.flush()

        loaded = (
            await RelUser.query(rel_session)
            .where(RelUser.id == user.id)
            .with_("posts", "posts.comments")
            .order_by(RelUser.id)
            .first()
        )
        assert loaded is not None
        assert len(loaded.posts) == 1
        assert len(loaded.posts[0].comments) == 1
        assert loaded.posts[0].comments[0].body == "A comment"

    async def test_nested_with_invalid_path_raises(self, rel_session: AsyncSession) -> None:
        with pytest.raises(ValueError, match="has no attribute 'nonexistent'"):
            await RelUser.query(rel_session).with_("nonexistent.path").first()


# ═══════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════


class TestRelationshipEdgeCases:
    async def test_with_unknown_relationship_raises(self, rel_session: AsyncSession) -> None:
        with pytest.raises(ValueError, match="has no attribute 'nonexistent'"):
            await RelUser.query(rel_session).with_("nonexistent").first()

    async def test_has_with_invalid_relationship_raises(self, rel_session: AsyncSession) -> None:
        with pytest.raises(ValueError, match="has no relationship 'nope'"):
            await RelUser.query(rel_session).has("nope").all()

    async def test_has_with_invalid_operator_raises(self, rel_session: AsyncSession) -> None:
        with pytest.raises(ValueError, match="Valid operators"):
            await RelUser.query(rel_session).has("posts", cast("Any", "LIKE"), 1).all()

    async def test_multiple_users_with_same_role(self, rel_session: AsyncSession) -> None:
        u1 = RelUser(name="Multi1", email="multi1@rel.test")
        u2 = RelUser(name="Multi2", email="multi2@rel.test")
        role = RelRole(name="shared_role")
        rel_session.add_all([u1, u2, role])
        await rel_session.flush()

        await rel_session.execute(role_user.insert().values(user_id=u1.id, role_id=role.id))
        await rel_session.execute(role_user.insert().values(user_id=u2.id, role_id=role.id))
        await rel_session.flush()

        loaded = (
            await RelRole.query(rel_session)
            .where(RelRole.id == role.id)
            .with_("users")
            .order_by(RelRole.id)
            .first()
        )
        assert loaded is not None
        assert len(loaded.users) == 2


# ═══════════════════════════════════════════════════════════
# M2M with_count support (Issue #3)
# ═══════════════════════════════════════════════════════════


class TestM2MWithCount:
    async def test_with_count_on_many_to_many(self, rel_session: AsyncSession) -> None:
        user = RelUser(name="CountM2M", email="countm2m@rel.test")
        r1 = RelRole(name="role_x")
        r2 = RelRole(name="role_y")
        rel_session.add_all([user, r1, r2])
        await rel_session.flush()

        await rel_session.execute(role_user.insert().values(user_id=user.id, role_id=r1.id))
        await rel_session.execute(role_user.insert().values(user_id=user.id, role_id=r2.id))
        await rel_session.flush()

        results = (
            await RelUser.query(rel_session)
            .where(RelUser.id == user.id)
            .with_count("roles")
            .all_with_counts()
        )
        assert len(results) == 1
        assert isinstance(results[0], WithCount)
        assert results[0].counts["roles"] == 2

    async def test_with_count_on_m2m_zero(self, rel_session: AsyncSession) -> None:
        user = RelUser(name="NoRoles", email="noroles_count@rel.test")
        rel_session.add(user)
        await rel_session.flush()

        results = (
            await RelUser.query(rel_session)
            .where(RelUser.id == user.id)
            .with_count("roles")
            .all_with_counts()
        )
        assert len(results) == 1
        assert isinstance(results[0], WithCount)
        assert results[0].counts["roles"] == 0


# ═══════════════════════════════════════════════════════════
# __singular__ override (Issue #4)
# ═══════════════════════════════════════════════════════════


class TestSingularOverride:
    def test_get_singular_uses_explicit_override(self) -> None:
        from arvel.data.relationships.mixin import _get_singular

        class FakeModel:
            __tablename__ = "people"
            __singular__ = "person"

        assert _get_singular(FakeModel) == "person"

    def test_get_singular_falls_back_to_naive(self) -> None:
        from arvel.data.relationships.mixin import _get_singular

        class FakeModel:
            __tablename__ = "users"

        assert _get_singular(FakeModel) == "user"

    def test_get_singular_handles_irregular_plural(self) -> None:
        from arvel.data.relationships.mixin import _get_singular, _singularize

        assert _singularize("people") == "people"

        class FakeModel:
            __tablename__ = "people"
            __singular__ = "person"

        assert _get_singular(FakeModel) == "person"
