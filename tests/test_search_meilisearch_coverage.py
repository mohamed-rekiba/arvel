"""arvel.search.MeilisearchEngine — driven against a fake ``meilisearch.Client``.

Exercises index/delete/search/flush/configure + the task-failure guard and the SearchManager
``create_meilisearch_driver`` seam, all without a running Meilisearch server.
"""

from __future__ import annotations

from typing import Any

import pytest

from arvel.search import MeilisearchEngine, SearchManager, SearchResult


class _Task:
    def __init__(self, uid: int, status: str = "succeeded", error: Any = None) -> None:
        self.task_uid = uid
        self.status = status
        self.error = error


class _FakeIndex:
    def __init__(self, store: dict[str, Any]) -> None:
        self.store = store
        self.next_task = _Task(1)

    def add_documents(self, docs: list[dict[str, Any]], primary_key: str, serializer: Any) -> _Task:
        self.store.setdefault("docs", []).extend(docs)
        self.store["primary_key"] = primary_key
        self.store["serializer"] = serializer
        return self.next_task

    def delete_document(self, key: Any) -> _Task:
        self.store["deleted"] = key
        return self.next_task

    def delete_all_documents(self) -> _Task:
        self.store["flushed"] = True
        return self.next_task

    def update_filterable_attributes(self, attrs: list[str]) -> _Task:
        self.store["filterable"] = attrs
        return self.next_task

    def update_sortable_attributes(self, attrs: list[str]) -> _Task:
        self.store["sortable"] = attrs
        return self.next_task

    def wait_for_task(self, uid: int) -> _Task:
        return self.next_task

    def search(self, query: str, options: dict[str, Any]) -> dict[str, Any]:
        self.store["last_search"] = (query, options)
        return {"hits": [{"_key": 1, "title": "hi"}], "estimatedTotalHits": 1}


class _FakeClient:
    def __init__(self, url: str, key: str | None) -> None:
        self.url = url
        self.key = key
        self.store: dict[str, Any] = {}
        self._index = _FakeIndex(self.store)

    def index(self, name: str) -> _FakeIndex:
        self.store["index_name"] = name
        return self._index


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> MeilisearchEngine:
    import meilisearch

    monkeypatch.setattr(meilisearch, "Client", _FakeClient)
    return MeilisearchEngine(url="http://meili:7700", key="masterkey")


async def test_index_writes_document_with_key_field(engine: MeilisearchEngine) -> None:
    await engine.index("articles", 7, {"title": "async python"})
    store = engine._client.store  # pyright: ignore[reportPrivateUsage]
    assert store["docs"] == [{"title": "async python", "_key": 7}]
    assert store["primary_key"] == "_key"


async def test_delete_and_flush(engine: MeilisearchEngine) -> None:
    await engine.delete("articles", 9)
    assert engine._client.store["deleted"] == 9  # pyright: ignore[reportPrivateUsage]
    await engine.flush("articles")
    assert engine._client.store["flushed"] is True  # pyright: ignore[reportPrivateUsage]


async def test_search_builds_filter_sort_limit_offset(engine: MeilisearchEngine) -> None:
    result = await engine.search(
        "articles",
        "python",
        filters=[("kind", "=", "post")],
        sort=["n:asc"],
        limit=5,
        offset=10,
    )
    assert isinstance(result, SearchResult)
    assert result.total == 1
    _query, options = engine._client.store["last_search"]  # pyright: ignore[reportPrivateUsage]
    assert options["filter"] == ['kind = "post"']
    assert options["sort"] == ["n:asc"]
    assert options["limit"] == 5
    assert options["offset"] == 10


async def test_search_rejects_injection_in_filter_field(engine: MeilisearchEngine) -> None:
    with pytest.raises(ValueError, match="unsafe search filter field"):
        await engine.search("articles", "x", filters=[("kind OR 1=1", "=", "post")])


async def test_configure_declares_attributes(engine: MeilisearchEngine) -> None:
    await engine.configure("articles", filterable=["kind"], sortable=["n"])
    store = engine._client.store  # pyright: ignore[reportPrivateUsage]
    assert store["filterable"] == ["kind"]
    assert store["sortable"] == ["n"]


async def test_configure_skips_empty_attribute_lists(engine: MeilisearchEngine) -> None:
    await engine.configure("articles", filterable=[], sortable=[])
    store = engine._client.store  # pyright: ignore[reportPrivateUsage]
    assert "filterable" not in store
    assert "sortable" not in store


async def test_failed_task_raises(engine: MeilisearchEngine) -> None:
    engine._client._index.next_task = _Task(  # pyright: ignore[reportPrivateUsage]
        2, status="failed", error="boom"
    )
    with pytest.raises(RuntimeError, match="Meilisearch task failed"):
        await engine.index("articles", 1, {"title": "x"})


def test_manager_create_meilisearch_driver_without_app() -> None:
    mgr = SearchManager()
    import meilisearch

    # patch so the driver can construct without a real server
    original = meilisearch.Client
    try:
        meilisearch.Client = _FakeClient  # type: ignore[assignment,misc]
        driver = mgr.create_meilisearch_driver()
        assert isinstance(driver, MeilisearchEngine)
    finally:
        meilisearch.Client = original  # type: ignore[misc]
