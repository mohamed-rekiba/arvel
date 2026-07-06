"""arvel.search.

A ``Searchable`` model is mirrored into a search index on save and removed on delete; querying
goes through the configured engine (``config('search.driver')``, default ``array``). The built-in
``ArrayEngine`` is an in-memory driver (the default + the test driver); ``MeilisearchEngine`` is an
optional driver behind the ``[search]`` extra. Engines are resolved by ``SearchManager`` (the
``arvel.support.manager.Manager`` strategy base).

``Model.search(query)`` returns a fluent:class:`SearchBuilder` (``where``/``order_by``/``take``/
``get``/``first``/``paginate``/``keys``/``raw``) — Scout parity. Index writes normally happen
inline on save/delete; setting ``search.queue = True`` instead emits a:class:`ModelIndexRequested`
event through the events dispatcher (see ``arvel.search.listeners`` for the provided listener) so
the write moves off the ``Searchable`` call path — the queue-seam story (no ``arvel.queue`` import
here; that back-edge is forbidden by the G1 layer contract).

Not part of the original ch-08 port spec — added on request as a first-party search module.
"""

from __future__ import annotations

import enum
import json
import re
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, Literal, Protocol, cast

from arvel.kernel import Settings
from arvel.support.manager import Manager, MissingExtraError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from arvel.pagination import LengthAwarePaginator

#: The field a hit's index key is carried under in every engine's search payload (both
#: ``ArrayEngine`` and ``MeilisearchEngine`` inject it) — the builder reads it back to hydrate.
_KEY_FIELD = "_key"


class _JSONEncoder(json.JSONEncoder):
    """JSON fallback for documents sent to Meilisearch — ``arvel.dates.Date``/``Enum``/anything
    with ``isoformat``. Structurally mirrors ``arvel.database.model``'s own ``_json_default``
    (duck-typed, not imported: search sits below database in the G1 layer DAG)."""

    def default(self, o: Any) -> Any:
        if isinstance(o, enum.Enum):
            return o.value
        if hasattr(o, "to_iso"):  # arvel Date
            return o.to_iso()
        if hasattr(o, "isoformat"):
            return o.isoformat()
        return super().default(o)


class SearchSettings(Settings):
    """Typed, validated view over the ``search`` config section (DR-0016)."""

    __config_key__ = "search"
    driver: str = "array"  # engine name (open registry → str)
    queue: bool = False  # True: save/delete emit ModelIndexRequested instead of an inline write


@dataclass(frozen=True, slots=True)
class SearchResult:
    """An engine's raw search payload: the matched ``hits`` (already filtered/sorted/sliced) and
    the ``total`` match count *before* slicing (so a paginator can report the grand total)."""

    hits: list[dict[str, Any]]
    total: int


class SearchEngine(Protocol):
    """The contract every search driver implements (index/delete/search/flush/configure)."""

    async def index(self, index: str, key: Any, record: dict[str, Any]) -> None: ...
    async def delete(self, index: str, key: Any) -> None: ...
    async def search(
        self,
        index: str,
        query: str,
        *,
        filters: Mapping[str, Any] | None = None,
        sort: Sequence[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> SearchResult: ...
    async def flush(self, index: str) -> None: ...
    async def configure(
        self, index: str, *, filterable: Sequence[str], sortable: Sequence[str]
    ) -> None: ...


_Hit = tuple[Any, dict[str, Any]]


def _sorted(hits: list[_Hit], sort: Sequence[str]) -> list[_Hit]:
    """Apply ``["field:asc", "field:desc",...]`` sort specs, last spec is the primary key
    (each pass is a stable sort, so applying right-to-left composes them /SQL-style)."""

    def _field_of(pair: _Hit, field: str) -> Any:
        return pair[1].get(field)

    ordered = list(hits)
    for spec in reversed(sort):
        field, _, direction = spec.partition(":")
        ordered.sort(key=partial(_field_of, field=field), reverse=(direction == "desc"))
    return ordered


class ArrayEngine:
    """In-memory engine — the default driver and the one used in tests. Search is a naive
    case-insensitive substring match over every value of each indexed record; ``filters`` are
    exact-match equality, ``sort``/``limit``/``offset`` slice the matched set in Python. No
    declared-attribute requirement (unlike Meilisearch) — ``configure`` is a no-op."""

    def __init__(self) -> None:
        self._store: dict[str, dict[Any, dict[str, Any]]] = {}

    async def index(self, index: str, key: Any, record: dict[str, Any]) -> None:
        self._store.setdefault(index, {})[key] = dict(record)

    async def delete(self, index: str, key: Any) -> None:
        self._store.get(index, {}).pop(key, None)

    async def search(
        self,
        index: str,
        query: str,
        *,
        filters: Mapping[str, Any] | None = None,
        sort: Sequence[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> SearchResult:
        needle = str(query).lower()
        matched = [
            (key, record)
            for key, record in self._store.get(index, {}).items()
            if any(needle in str(value).lower() for value in record.values())
        ]
        if filters:
            matched = [
                (key, record)
                for key, record in matched
                if all(record.get(field) == value for field, value in filters.items())
            ]
        if sort:
            matched = _sorted(matched, sort)
        total = len(matched)
        if offset:
            matched = matched[offset:]
        if limit is not None:
            matched = matched[:limit]
        hits = [{**record, _KEY_FIELD: key} for key, record in matched]
        return SearchResult(hits=hits, total=total)

    async def flush(self, index: str) -> None:
        self._store.pop(index, None)

    async def configure(
        self, index: str, *, filterable: Sequence[str], sortable: Sequence[str]
    ) -> None:
        """No-op: the in-memory engine filters/sorts on any field, declared or not."""


_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def _safe_field(field: str) -> str:
    """A filter field must be a bare identifier — never request-derived free text — so it can't
    inject Meilisearch filter-expression syntax."""
    if not _FIELD_RE.match(field):
        raise ValueError(f"unsafe search filter field: {field!r}")
    return field


def _filter_value(value: Any) -> str:
    """Render a filter value as a Meilisearch literal. bool/None must be the engine's
    ``true``/``false``/``null`` — Python's ``repr`` would emit ``True``/``None`` and silently
    never match. bool is checked before int since ``bool`` subclasses ``int``."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return repr(value)
    return repr(str(value))  # quoted string literal


class MeilisearchEngine:
    """Meilisearch-backed engine (optional ``[search]`` extra). Construction fails with
    ``MissingExtraError`` when the ``meilisearch`` client isn't installed.

    The ``meilisearch`` client is synchronous; every call runs in a worker thread
    (``anyio.to_thread.run_sync``) so it never blocks the event loop. Writes wait for their
    server-side task to finish before returning — trading a little write latency for
    read-your-writes consistency (Meilisearch indexing is otherwise async)."""

    def __init__(self, url: str = "http://localhost:7700", key: str | None = None) -> None:
        try:
            import meilisearch
        except ImportError as exc:  # pragma: no cover - exercised via SearchManager
            raise MissingExtraError("meilisearch", "search") from exc
        self._client = meilisearch.Client(url, key)

    async def index(self, index: str, key: Any, record: dict[str, Any]) -> None:
        from anyio.to_thread import run_sync

        document = {**record, _KEY_FIELD: key}

        def _write() -> None:
            idx = self._client.index(index)
            # explicit primary_key: don't rely on Meilisearch inferring one from the record's own
            # fields (it may have none ending in "id") — `_key` is always the id we index by.
            task = idx.add_documents([document], primary_key=_KEY_FIELD, serializer=_JSONEncoder)
            self._raise_if_failed(idx.wait_for_task(task.task_uid))

        await run_sync(_write)

    async def delete(self, index: str, key: Any) -> None:
        from anyio.to_thread import run_sync

        def _delete() -> None:
            idx = self._client.index(index)
            task = idx.delete_document(key)
            self._raise_if_failed(idx.wait_for_task(task.task_uid))

        await run_sync(_delete)

    async def search(
        self,
        index: str,
        query: str,
        *,
        filters: Mapping[str, Any] | None = None,
        sort: Sequence[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> SearchResult:
        from anyio.to_thread import run_sync

        options: dict[str, Any] = {}
        if filters:
            # equality filters only (scope of this story); values are repr()'d into Meilisearch's
            # filter-expression syntax. Field names are interpolated raw, so guard them: only a
            # bare identifier is allowed — never request-derived free text (filter-injection).
            options["filter"] = [
                f"{_safe_field(field)} = {_filter_value(value)}" for field, value in filters.items()
            ]
        if sort:
            options["sort"] = list(sort)
        if limit is not None:
            options["limit"] = limit
        if offset is not None:
            options["offset"] = offset

        def _search() -> dict[str, Any]:
            return self._client.index(index).search(query, options)

        payload = await run_sync(_search)
        hits = cast("list[dict[str, Any]]", payload["hits"])
        total = int(payload.get("estimatedTotalHits", payload.get("nbHits", len(hits))))
        return SearchResult(hits=hits, total=total)

    async def flush(self, index: str) -> None:
        from anyio.to_thread import run_sync

        def _flush() -> None:
            idx = self._client.index(index)
            task = idx.delete_all_documents()
            self._raise_if_failed(idx.wait_for_task(task.task_uid))

        await run_sync(_flush)

    async def configure(
        self, index: str, *, filterable: Sequence[str], sortable: Sequence[str]
    ) -> None:
        """Declare ``filterable``/``sortable`` attributes — Meilisearch only honors ``where``/
        ``order_by`` on fields declared this way (``scout:import`` calls this)."""
        from anyio.to_thread import run_sync

        def _configure() -> None:
            idx = self._client.index(index)
            if filterable:
                task = idx.update_filterable_attributes(list(filterable))
                self._raise_if_failed(idx.wait_for_task(task.task_uid))
            if sortable:
                task = idx.update_sortable_attributes(list(sortable))
                self._raise_if_failed(idx.wait_for_task(task.task_uid))

        await run_sync(_configure)

    @staticmethod
    def _raise_if_failed(task: Any) -> None:
        if getattr(task, "status", None) == "failed":
            raise RuntimeError(f"Meilisearch task failed: {getattr(task, 'error', task)!r}")


class SearchManager(Manager):
    """Resolves the configured search engine. Default driver: ``config('search.driver')`` or
    ``array``. Forwards unknown attributes to the default driver (``Manager`` base)."""

    def default_driver(self) -> str:
        return SearchSettings().driver  # auto-loads + validates config("search")

    def create_array_driver(self) -> ArrayEngine:
        return ArrayEngine()

    def create_meilisearch_driver(self) -> MeilisearchEngine:
        config: Mapping[str, Any] = {}
        if self.app is not None and self.app.bound("config"):
            config = self.app.make("config").get("search.meilisearch", {}) or {}
        return MeilisearchEngine(**config)


@dataclass(frozen=True, slots=True)
class ModelIndexRequested:
    """Emitted (instead of an inline engine write) when ``search.queue`` is enabled — carries
    everything a listener needs to perform the write later: the model class (for
    ``searchable_as()``), the index key, and the record (``None`` means "delete this key").

    Ships with a provided listener (``arvel.search.listeners.handle_index_request``) that performs
    the write when the event fires — proving the seam end-to-end. Running that off a real worker
    (rather than inline in the dispatch call) rides on the queue's own story (QUEUE-RELIABILITY);
    this module never imports ``arvel.queue`` (G1 boundary)."""

    model_class: type[Any]
    key: Any
    record: dict[str, Any] | None


class Searchable:
    """Mixin that makes a model searchable (Scout-style): it is indexed on save and removed on
    delete, and ``Model.search(query)`` returns a fluent:class:`SearchBuilder`. Override
    ``to_searchable_array`` to control what gets indexed, ``searchable_as`` to name the index, and
    ``searchable_filterable``/``searchable_sortable`` to declare the fields ``where``/``order_by``
    need on Meilisearch (``scout:import`` pushes them as index settings)."""

    def to_searchable_array(self) -> dict[str, Any]:
        """The record to index — the model's serialized form by default."""
        data = cast("dict[str, Any]", self.to_dict())  # type: ignore[attr-defined]
        return data

    @classmethod
    def searchable_as(cls) -> str:
        """The index name — the model's table name by default."""
        return str(cls.__table__.name)  # type: ignore[attr-defined]

    @classmethod
    def searchable_filterable(cls) -> list[str]:
        """Fields Meilisearch should index as filterable (``where`` needs this). Default: none."""
        return []

    @classmethod
    def searchable_sortable(cls) -> list[str]:
        """Fields Meilisearch should index as sortable (``order_by`` needs this). Default: none."""
        return []

    def get_search_key(self) -> Any:
        """The index document key — the model's primary key by default."""
        return getattr(self, type(self).__primary_key__)  # type: ignore[attr-defined]

    @staticmethod
    def _search_engine() -> Any:
        from arvel.kernel import app, has_application

        return app("search") if has_application() and app().bound("search") else None

    @staticmethod
    def _events_dispatcher() -> Any:
        from arvel.kernel import app, has_application

        return app("events") if has_application() and app().bound("events") else None

    async def _sync_to_index(self, record: dict[str, Any] | None) -> None:
        """Write ``record`` (``None`` = delete) to the index — inline by default, or via a
        :class:`ModelIndexRequested` event when ``search.queue`` is enabled."""
        if SearchSettings().queue:
            dispatcher = self._events_dispatcher()
            if dispatcher is None:
                # queued indexing configured but nothing can carry the event — that's a
                # dropped index write; fail loudly rather than silently lose the update
                raise RuntimeError(
                    "search.queue is enabled but no event dispatcher is bound; "
                    "register one (or disable search.queue) so index writes aren't lost"
                )
            event = ModelIndexRequested(type(self), self.get_search_key(), record)
            await dispatcher.dispatch(event)
            return
        engine = self._search_engine()
        if engine is None:
            return
        if record is None:
            await engine.delete(self.searchable_as(), self.get_search_key())
        else:
            await engine.index(self.searchable_as(), self.get_search_key(), record)

    async def searchable(self) -> None:
        """Index (or re-index) this record now (respects ``search.queue``)."""
        await self._sync_to_index(self.to_searchable_array())

    async def unsearchable(self) -> None:
        """Remove this record from the index now (respects ``search.queue``)."""
        await self._sync_to_index(None)

    @classmethod
    async def make_all_searchable(cls) -> int:
        """Index every row of this model (Scout's ``makeAllSearchable``). Returns the number of
        records indexed. Use it to (re)build the index after a bulk load / seed. ``scout:import``
        (the CLI command) chunks instead, for large tables."""
        records = cast("list[Any]", await cls.all())  # type: ignore[attr-defined]
        for record in records:
            await record.searchable()
        return len(records)

    @classmethod
    async def remove_all_from_search(cls) -> None:
        """Remove every row of this model from the index (Scout's ``scout:flush``)."""
        engine = cls._search_engine()
        if engine is not None:
            await engine.flush(cls.searchable_as())

    @classmethod
    def search(cls, query: str) -> SearchBuilder[Any]:
        """Start a fluent search query:
        ``Model.search('term').where('field', v).order_by('n', 'desc').paginate(per_page=10)``."""
        return SearchBuilder(cls, query)

    async def _fire(self, hook: str) -> Any:
        result = cast("Any", await super()._fire(hook))  # type: ignore[misc]
        if hook == "saved":
            await self.searchable()
        elif hook == "deleted":
            await self.unsearchable()
        elif hook == "restored":
            # Scout parity: restoring a soft-deleted model makes it searchable again
            await self.searchable()
        return result


class SearchBuilder[M: Searchable]:
    """Fluent search-query builder returned by ``Model.search(query)``.

    ``where``/``order_by``/``take`` build up the query; ``get``/``first``/``paginate`` run it and
    hydrate hits back into models (by primary key, preserving the engine's result order — a
    ``whereIn(pk, keys)`` fetch, mirroring); ``keys``/``raw`` skip hydration for the raw
    engine keys/payload. Soft-deleted models are excluded unless ``with_trashed()`` was called."""

    def __init__(self, model_cls: type[M], query: str) -> None:
        self._model_cls = model_cls
        self._query = query
        self._filters: dict[str, Any] = {}
        self._sort: list[str] = []
        self._limit: int | None = None
        self._with_trashed = False

    def where(self, field: str, value: Any) -> SearchBuilder[M]:
        """Add an equality filter (Meilisearch: ``field`` must be declared filterable)."""
        self._filters[field] = value
        return self

    def order_by(self, field: str, direction: Literal["asc", "desc"] = "asc") -> SearchBuilder[M]:
        """Sort hits by ``field`` (Meilisearch: ``field`` must be declared sortable)."""
        self._sort.append(f"{field}:{direction}")
        return self

    def take(self, limit: int) -> SearchBuilder[M]:
        """Cap ``get()``/``raw()`` to at most ``limit`` hits."""
        self._limit = limit
        return self

    def with_trashed(self) -> SearchBuilder[M]:
        """Include soft-deleted models when hydrating (default: excluded)."""
        self._with_trashed = True
        return self

    async def _search(self, *, limit: int | None, offset: int | None) -> SearchResult:
        engine = cast("Any", self._model_cls)._search_engine()
        if engine is None:
            return SearchResult(hits=[], total=0)
        index = cast("Any", self._model_cls).searchable_as()
        return cast(
            "SearchResult",
            await engine.search(
                index,
                self._query,
                filters=self._filters or None,
                sort=self._sort or None,
                limit=limit,
                offset=offset,
            ),
        )

    async def raw(self) -> SearchResult:
        """The engine's raw payload for the current query (respects ``take()``; no page offset)."""
        return await self._search(limit=self._limit, offset=None)

    async def keys(self) -> list[Any]:
        """The matched records' raw index keys, unhydrated, in engine order."""
        result = await self.raw()
        return [hit[_KEY_FIELD] for hit in result.hits]

    async def _hydrate(self, hits: list[dict[str, Any]]) -> list[M]:
        if not hits:
            return []
        keys = [hit[_KEY_FIELD] for hit in hits]
        model_cls = cast("Any", self._model_cls)
        query = model_cls.with_trashed() if self._with_trashed else model_cls.query()
        rows = await query.where_in(model_cls.__primary_key__, keys).get()
        by_key = {getattr(row, model_cls.__primary_key__): row for row in rows}
        # preserve the engine's hit order; a row missing from the DB (e.g. a stale index entry)
        # is silently dropped rather than raising.
        return [by_key[key] for key in keys if key in by_key]

    async def get(self) -> list[M]:
        """Run the query and return hydrated models, in engine order."""
        result = await self.raw()
        return await self._hydrate(result.hits)

    async def first(self) -> M | None:
        """The first hydrated match, or ``None``."""
        result = await self._search(limit=1, offset=0)
        hydrated = await self._hydrate(result.hits)
        return hydrated[0] if hydrated else None

    async def paginate(self, per_page: int = 15, page: int | None = None) -> LengthAwarePaginator:
        """A length-aware paginator (DR-0022) over the hydrated matches. ``page`` defaults to the
        current request's ``?page=`` (1 outside a request)."""
        from arvel.pagination import LengthAwarePaginator, resolve_current_page

        per_page = max(1, per_page)
        if page is None:
            page = resolve_current_page()
        result = await self._search(limit=per_page, offset=(page - 1) * per_page)
        items = await self._hydrate(result.hits)
        return LengthAwarePaginator(items, result.total, per_page, page)


__all__ = [
    "ArrayEngine",
    "MeilisearchEngine",
    "ModelIndexRequested",
    "SearchBuilder",
    "SearchEngine",
    "SearchManager",
    "SearchResult",
    "SearchSettings",
    "Searchable",
]
