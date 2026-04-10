"""SearchObserver — auto-syncs Searchable models to the search engine.

Registered by ``SearchProvider.boot()`` against all models that use
the ``Searchable`` mixin. Hooks into the existing ``ObserverRegistry``
lifecycle events.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeGuard

from arvel.search.mixin import Searchable

if TYPE_CHECKING:
    from arvel.data.model import ArvelModel
    from arvel.search.contracts import SearchEngine


def _is_searchable(instance: ArvelModel) -> TypeGuard[Searchable]:
    return isinstance(instance, Searchable)


class SearchObserver:
    """Observes model lifecycle events and syncs to the search engine.

    Only acts on instances that are ``Searchable``. Non-searchable
    models pass through silently.

    The observer is registered with low priority (90) so it runs
    after business-logic observers.
    """

    def __init__(self, engine: SearchEngine) -> None:
        self._engine = engine

    async def created(self, instance: ArvelModel) -> None:
        """Index the instance after creation."""
        if not _is_searchable(instance):
            return
        index = instance.search_index_name()
        doc = instance.to_searchable_array()
        await self._engine.upsert_documents(index, [doc])

    async def updated(self, instance: ArvelModel) -> None:
        """Re-index the instance after update."""
        if not _is_searchable(instance):
            return
        index = instance.search_index_name()
        doc = instance.to_searchable_array()
        await self._engine.upsert_documents(index, [doc])

    async def deleted(self, instance: ArvelModel) -> None:
        """Remove the instance from the index after deletion."""
        if not _is_searchable(instance):
            return
        index = instance.search_index_name()
        doc_id = instance.searchable_id()
        await self._engine.remove_documents(index, [doc_id])
