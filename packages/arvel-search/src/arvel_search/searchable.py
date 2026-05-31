"""Searchable mixin — make any Arvel model indexable and queryable.

Add ``Searchable`` to a model and declare ``__searchable__`` to gain a
``search()`` entry point plus automatic index sync on create/update/delete.
Only the columns listed in ``__searchable__`` are indexed, so sensitive
columns never leak into the search backend.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, ClassVar, Self

from arvel_search.builder import SearchBuilder
from arvel_search.facade import Search

if TYPE_CHECKING:
    from arvel_search.engine import Engine

# Column names that should never be indexed. Declaring one in __searchable__
# is almost always a mistake, so we warn loudly at class-definition time.
_SENSITIVE_FIELDS = frozenset(
    {"password", "password_hash", "remember_token", "secret", "token", "api_key", "private_key"}
)


def _active_engine() -> Engine | None:
    return Search.active_engine_or_none()


def _queue_sync_enabled() -> bool:
    manager = Search.manager
    return manager is not None and not Search.is_faked() and manager.config.queue_sync


def _sync_enabled() -> bool:
    if Search.is_faked():
        return True
    manager = Search.manager
    return manager is None or manager.config.sync_on_save


class Searchable:
    """Mixin granting a model search indexing and a fluent query API."""

    __search_index__: ClassVar[str | None] = None
    __search_key__: ClassVar[str] = "id"
    __searchable__: ClassVar[tuple[str, ...] | list[str]] = ()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        leaked = _SENSITIVE_FIELDS & {str(f) for f in cls.__searchable__}
        if leaked:
            warnings.warn(
                f"{cls.__name__}.__searchable__ includes sensitive field(s) {sorted(leaked)}; "
                "these will be sent to the search backend in plaintext.",
                stacklevel=2,
            )
        on = getattr(cls, "on", None)
        if on is None:
            return
        on("created", _on_save)
        on("updated", _on_save)
        on("restored", _on_save)
        on("deleted", _on_delete)

    @classmethod
    def search_index_name(cls) -> str:
        if cls.__search_index__:
            return cls.__search_index__
        table = getattr(cls, "__tablename__", None)
        return table if isinstance(table, str) else cls.__name__.lower()

    @classmethod
    def search_key_name(cls) -> str:
        return cls.__search_key__

    @classmethod
    def searchable_columns(cls) -> tuple[str, ...]:
        return tuple(cls.__searchable__)

    @classmethod
    def search(cls, query: str = "") -> SearchBuilder[Self]:
        return SearchBuilder(cls, query)

    def searchable_id(self) -> str:
        return str(getattr(self, type(self).search_key_name()))

    def to_searchable_array(self) -> dict[str, Any]:
        """Indexed payload: the key plus every column in ``__searchable__``.

        Override to compute derived fields, but keep it to non-sensitive data.
        """
        cls = type(self)
        key_name = cls.search_key_name()
        array: dict[str, Any] = {key_name: getattr(self, key_name)}
        for column in cls.__searchable__:
            array[str(column)] = getattr(self, column)
        return array

    async def searchable(self) -> None:
        """Index (or re-index) this instance now, ignoring ``sync_on_save``."""
        engine = _active_engine()
        if engine is not None:
            cls = type(self)
            await engine.upsert_documents(
                cls.search_index_name(), [self.to_searchable_array()], key=cls.search_key_name()
            )

    async def unsearchable(self) -> None:
        """Remove this instance from its index now."""
        engine = _active_engine()
        if engine is not None:
            await engine.remove_documents(type(self).search_index_name(), [self.searchable_id()])

    @classmethod
    async def make_all_searchable(cls) -> int:
        """Index every row of this model. Returns the count indexed."""
        engine = _active_engine()
        if engine is None:
            return 0
        model: Any = cls
        rows: list[Self] = await model.query().get()
        if not rows:
            return 0
        documents = [row.to_searchable_array() for row in rows]
        await engine.upsert_documents(cls.search_index_name(), documents, key=cls.search_key_name())
        return len(rows)

    @classmethod
    async def remove_all_from_search(cls) -> None:
        """Flush this model's entire index."""
        engine = _active_engine()
        if engine is not None:
            await engine.flush(cls.search_index_name())


async def _on_save(instance: Searchable) -> None:
    if not _sync_enabled():
        return
    if _queue_sync_enabled():
        await _dispatch_index_job(instance)
        return
    await instance.searchable()


async def _on_delete(instance: Searchable) -> None:
    if not _sync_enabled():
        return
    if _queue_sync_enabled():
        await _dispatch_remove_job(instance)
        return
    await instance.unsearchable()


async def _dispatch_index_job(instance: Searchable) -> None:
    from arvel.facades.bus import Bus

    from arvel_search.jobs import SearchIndexJob

    cls = type(instance)
    await Bus.dispatch(
        SearchIndexJob(
            model_module=cls.__module__,
            model_qualname=cls.__qualname__,
            keys=[instance.searchable_id()],
        )
    )


async def _dispatch_remove_job(instance: Searchable) -> None:
    from arvel.facades.bus import Bus

    from arvel_search.jobs import SearchRemoveJob

    cls = type(instance)
    await Bus.dispatch(
        SearchRemoveJob(
            model_module=cls.__module__,
            model_qualname=cls.__qualname__,
            keys=[instance.searchable_id()],
        )
    )


__all__ = ["Searchable"]
