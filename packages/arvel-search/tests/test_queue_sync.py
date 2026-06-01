"""Queued index sync — SEARCH_QUEUE_SYNC dispatches jobs instead of inline sync."""

from __future__ import annotations

from typing import Any

import pytest
from arvel.facades.bus import Bus
from arvel.queue.job import Job
from arvel_search import Search, SearchManager
from arvel_search.jobs import SearchIndexJob, SearchRemoveJob
from search_support import Article, make_config
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def captured_jobs(monkeypatch: pytest.MonkeyPatch) -> list[Job]:
    jobs: list[Job] = []

    async def fake_dispatch(_cls: type[Bus], job: Job) -> None:
        jobs.append(job)

    monkeypatch.setattr(Bus, "dispatch", classmethod(fake_dispatch))
    return jobs


class TestQueuedSync:
    async def test_save_dispatches_index_job(
        self, tables: None, session: AsyncSession, captured_jobs: list[Job]
    ) -> None:
        Search.bind(SearchManager(make_config(driver="collection", queue_sync=True)))
        article = await Article.create(title="Queued", body="x")

        assert len(captured_jobs) == 1
        job = captured_jobs[0]
        assert isinstance(job, SearchIndexJob)
        assert job.keys == [str(article.id)]
        assert job.model_qualname == "Article"

    async def test_delete_dispatches_remove_job(
        self, tables: None, session: AsyncSession, captured_jobs: list[Job]
    ) -> None:
        Search.bind(SearchManager(make_config(driver="collection", queue_sync=True)))
        article = await Article.create(title="Drop", body="x")
        captured_jobs.clear()
        await article.delete()

        assert len(captured_jobs) == 1
        assert isinstance(captured_jobs[0], SearchRemoveJob)


class TestJobHandlers:
    async def test_index_job_reindexes_from_db(self, tables: None, session: AsyncSession) -> None:
        manager = SearchManager(make_config(driver="collection", sync_on_save=False))
        Search.bind(manager)
        article = await Article.create(title="Rebuild me", body="x")

        job: Any = SearchIndexJob(
            model_module=Article.__module__,
            model_qualname=Article.__qualname__,
            keys=[str(article.id)],
        )
        await job.handle()

        from arvel_search.dtos import SearchQuery

        query = SearchQuery(index="search_articles", query="rebuild")
        result = await manager.engine().search(query)
        assert result.ids == [str(article.id)]

    async def test_remove_job_drops_key(self, tables: None, session: AsyncSession) -> None:
        manager = SearchManager(make_config(driver="collection"))
        Search.bind(manager)
        article = await Article.create(title="Bye", body="x")

        remove: Any = SearchRemoveJob(
            model_module=Article.__module__,
            model_qualname=Article.__qualname__,
            keys=[str(article.id)],
        )
        await remove.handle()

        from arvel_search.dtos import SearchQuery

        result = await manager.engine().search(SearchQuery(index="search_articles", query="bye"))
        assert result.ids == []
