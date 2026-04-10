"""Tests for soft-delete behavior — SoftDeletes mixin, query filtering, restore, force_delete."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import String, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column  # noqa: TC002

from arvel.data.model import ArvelModel
from arvel.data.observer import ModelObserver, ObserverRegistry
from arvel.data.repository import Repository
from arvel.data.soft_deletes import SoftDeletes
from arvel.data.transaction import Transaction

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


# ──── Models ────


class Article(SoftDeletes, ArvelModel):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))


class HardDeleteItem(ArvelModel):
    """Model without soft deletes for comparison."""

    __tablename__ = "hard_delete_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))


# ──── Repositories / Transaction ────


class ArticleRepository(Repository[Article]):
    pass


class HardDeleteItemRepository(Repository[HardDeleteItem]):
    pass


class SoftDeleteTransaction(Transaction):
    articles: ArticleRepository
    items: HardDeleteItemRepository


# ──── Fixtures ────


@pytest.fixture(scope="module", params=["asyncio"], autouse=True)
def anyio_backend(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture
async def sd_session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

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


@pytest.fixture
def observer_registry() -> ObserverRegistry:
    return ObserverRegistry()


@pytest.fixture
def tx(sd_session: AsyncSession, observer_registry: ObserverRegistry) -> SoftDeleteTransaction:
    return SoftDeleteTransaction(session=sd_session, observer_registry=observer_registry)


async def _seed_articles(tx: SoftDeleteTransaction) -> list[Article]:
    articles = []
    async with tx:
        for title in ("Alpha", "Beta", "Gamma"):
            a = await tx.articles.create({"title": title})
            articles.append(a)
    return articles


# ──── Soft delete behavior ────


class TestSoftDeleteBasic:
    async def test_delete_sets_deleted_at_instead_of_removing(
        self, sd_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        tx = SoftDeleteTransaction(session=sd_session, observer_registry=observer_registry)
        async with tx:
            article = await tx.articles.create({"title": "Deletable"})
            assert article.deleted_at is None

            await tx.articles.delete(article.id)

            # Row still exists — soft deleted
            all_incl_trashed = await Article.query(sd_session).with_trashed().all()
            found = [a for a in all_incl_trashed if a.id == article.id]
            assert len(found) == 1
            assert found[0].deleted_at is not None

    async def test_deleted_rows_excluded_from_default_queries(
        self, sd_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        tx = SoftDeleteTransaction(session=sd_session, observer_registry=observer_registry)
        async with tx:
            a1 = await tx.articles.create({"title": "Visible"})
            a2 = await tx.articles.create({"title": "Invisible"})
            await tx.articles.delete(a2.id)

            result = await Article.query(sd_session).all()
            ids = [a.id for a in result]
            assert a1.id in ids
            assert a2.id not in ids

    async def test_find_excludes_soft_deleted(
        self, sd_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        from arvel.data.exceptions import NotFoundError

        tx = SoftDeleteTransaction(session=sd_session, observer_registry=observer_registry)
        async with tx:
            article = await tx.articles.create({"title": "Gone"})
            await tx.articles.delete(article.id)

            with pytest.raises(NotFoundError):
                await tx.articles.find(article.id)


class TestWithTrashed:
    async def test_with_trashed_includes_soft_deleted(
        self, sd_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        tx = SoftDeleteTransaction(session=sd_session, observer_registry=observer_registry)
        async with tx:
            await tx.articles.create({"title": "Active"})
            a2 = await tx.articles.create({"title": "Trashed"})
            await tx.articles.delete(a2.id)

            all_rows = await Article.query(sd_session).with_trashed().all()
            assert len(all_rows) == 2


class TestOnlyTrashed:
    async def test_only_trashed_returns_soft_deleted_only(
        self, sd_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        tx = SoftDeleteTransaction(session=sd_session, observer_registry=observer_registry)
        async with tx:
            await tx.articles.create({"title": "Active"})
            a2 = await tx.articles.create({"title": "Trashed"})
            await tx.articles.delete(a2.id)

            trashed = await Article.query(sd_session).only_trashed().all()
            assert len(trashed) == 1
            assert trashed[0].id == a2.id


class TestRestore:
    async def test_restore_clears_deleted_at(
        self, sd_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        tx = SoftDeleteTransaction(session=sd_session, observer_registry=observer_registry)
        async with tx:
            article = await tx.articles.create({"title": "Restorable"})
            await tx.articles.delete(article.id)

            restored = await tx.articles.restore(article.id)
            assert restored.deleted_at is None

            found = await tx.articles.find(restored.id)
            assert found is not None

    async def test_restore_on_non_soft_delete_model_raises_type_error(
        self, sd_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        tx = SoftDeleteTransaction(session=sd_session, observer_registry=observer_registry)
        async with tx:
            item = await tx.items.create({"name": "Test"})
            with pytest.raises(TypeError, match="does not support soft deletes"):
                await tx.items.restore(item.id)


class TestForceDelete:
    async def test_force_delete_permanently_removes(
        self, sd_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        tx = SoftDeleteTransaction(session=sd_session, observer_registry=observer_registry)
        async with tx:
            article = await tx.articles.create({"title": "Permanent"})
            await tx.articles.force_delete(article.id)

            all_rows = await Article.query(sd_session).with_trashed().all()
            ids = [a.id for a in all_rows]
            assert article.id not in ids

    async def test_force_delete_on_soft_deleted_record(
        self, sd_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        tx = SoftDeleteTransaction(session=sd_session, observer_registry=observer_registry)
        async with tx:
            article = await tx.articles.create({"title": "SoftThenHard"})
            await tx.articles.delete(article.id)
            await tx.articles.force_delete(article.id)

            all_rows = await Article.query(sd_session).with_trashed().all()
            ids = [a.id for a in all_rows]
            assert article.id not in ids


class TestHardDeleteUnchanged:
    async def test_model_without_soft_deletes_hard_deletes(
        self, sd_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        tx = SoftDeleteTransaction(session=sd_session, observer_registry=observer_registry)
        async with tx:
            item = await tx.items.create({"name": "DeleteMe"})
            await tx.items.delete(item.id)

            all_items = await HardDeleteItem.query(sd_session).all()
            ids = [i.id for i in all_items]
            assert item.id not in ids


class TestSoftDeleteObservers:
    async def test_deleting_deleted_events_fire_on_soft_delete(
        self, sd_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        events: list[str] = []

        class TrackingObserver(ModelObserver[Article]):
            async def deleting(self, instance: Article) -> bool:
                events.append("deleting")
                return True

            async def deleted(self, instance: Article) -> None:
                events.append("deleted")

        observer_registry.register(Article, TrackingObserver())
        tx = SoftDeleteTransaction(session=sd_session, observer_registry=observer_registry)
        async with tx:
            article = await tx.articles.create({"title": "Observed"})
            await tx.articles.delete(article.id)

        assert "deleting" in events
        assert "deleted" in events

    async def test_force_deleting_events_fire(
        self, sd_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        events: list[str] = []

        class TrackingObserver(ModelObserver[Article]):
            async def force_deleting(self, instance: Article) -> bool:
                events.append("force_deleting")
                return True

            async def force_deleted(self, instance: Article) -> None:
                events.append("force_deleted")

        observer_registry.register(Article, TrackingObserver())
        tx = SoftDeleteTransaction(session=sd_session, observer_registry=observer_registry)
        async with tx:
            article = await tx.articles.create({"title": "ForceObserved"})
            await tx.articles.force_delete(article.id)

        assert "force_deleting" in events
        assert "force_deleted" in events

    async def test_restoring_restored_events_fire(
        self, sd_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        events: list[str] = []

        class TrackingObserver(ModelObserver[Article]):
            async def restoring(self, instance: Article) -> bool:
                events.append("restoring")
                return True

            async def restored(self, instance: Article) -> None:
                events.append("restored")

        observer_registry.register(Article, TrackingObserver())
        tx = SoftDeleteTransaction(session=sd_session, observer_registry=observer_registry)
        async with tx:
            article = await tx.articles.create({"title": "RestoreObserved"})
            await tx.articles.delete(article.id)
            await tx.articles.restore(article.id)

        assert "restoring" in events
        assert "restored" in events


class TestTrashedProperty:
    async def test_trashed_property_true_when_soft_deleted(
        self, sd_session: AsyncSession, observer_registry: ObserverRegistry
    ) -> None:
        tx = SoftDeleteTransaction(session=sd_session, observer_registry=observer_registry)
        async with tx:
            article = await tx.articles.create({"title": "CheckProp"})
            assert not article.trashed

            await tx.articles.delete(article.id)

            trashed_list = await Article.query(sd_session).only_trashed().all()
            assert trashed_list[0].trashed is True
