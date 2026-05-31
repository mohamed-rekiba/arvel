"""Queued index-sync jobs (used when ``SEARCH_QUEUE_SYNC=true``)."""

from __future__ import annotations

import importlib
from typing import Any

from arvel.queue.job import Job

from arvel_search.facade import Search


def _resolve_model(module: str, qualname: str) -> Any:
    obj: Any = importlib.import_module(module)
    for part in qualname.split("."):
        obj = getattr(obj, part)
    return obj


class SearchIndexJob(Job):
    """Re-index a batch of records, fetched fresh from the DB by key.

    Carries the model's import path (not the instance) so it survives the
    broker round-trip. The worker re-loads the rows so the index reflects
    committed state, not stale in-flight data.
    """

    queue: str = "search"
    model_module: str
    model_qualname: str
    keys: list[str]

    async def handle(self) -> None:
        model = _resolve_model(self.model_module, self.model_qualname)
        key_attr = getattr(model, model.search_key_name())
        rows: list[Any] = await model.query().where_in(key_attr, self.keys).get()
        if not rows:
            return
        documents = [row.to_searchable_array() for row in rows]
        await Search.engine().upsert_documents(
            model.search_index_name(), documents, key=model.search_key_name()
        )


class SearchRemoveJob(Job):
    """Remove a batch of keys from a model's index."""

    queue: str = "search"
    model_module: str
    model_qualname: str
    keys: list[str]

    async def handle(self) -> None:
        model = _resolve_model(self.model_module, self.model_qualname)
        await Search.engine().remove_documents(model.search_index_name(), self.keys)


__all__ = ["SearchIndexJob", "SearchRemoveJob"]
