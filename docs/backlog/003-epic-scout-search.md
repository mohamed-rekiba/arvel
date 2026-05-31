# Epic 003: Scout-Style Search (`arvel-search`)

## Summary

A new companion package (`arvel-search`) that brings Scout-style full-text search to arvel.
Models implement a `Searchable` mixin to auto-sync documents to a search index on create/update/delete.
A fluent `SearchBuilder` handles query construction. Swappable drivers (Meilisearch, Elasticsearch,
database, collection, null) mean apps can change search infrastructure via config with no code changes.
Fixes two critical bugs from `arvel_old`: `Searchable.search()` was hardcoded to `NullEngine`, and
`SearchProvider.boot()` never registered the observer.

---

## Stories

### Story 1: `Searchable` mixin with automatic index sync

**As a** framework user,
**I want** to add a `Searchable` mixin to my model and declare `__searchable__` fields,
**so that** the model's documents are automatically indexed (or removed) when records are created, updated, or deleted — without writing observer code myself.

**Acceptance Criteria**:
- [ ] Given a model declares `class Article(Model, Searchable): __searchable__ = ["title", "body"]`, when a new `Article` is saved, then `SearchObserver.created()` calls `engine.upsert_documents([article.to_searchable_array()])`
- [ ] Given an `Article` is updated, when the record is saved, then `SearchObserver.updated()` re-indexes the document using `article.searchable_id()` as the key
- [ ] Given an `Article` is deleted, when the record is removed, then `SearchObserver.deleted()` calls `engine.remove_documents([article.searchable_id()])`
- [ ] Given a model does not implement `Searchable`, when the observer processes it, then the event is silently ignored
- [ ] Given `__search_index__` is not declared, when `search_index_name()` is called, then it returns the plural snake_case table name (e.g., `articles`)
- [ ] Given `SearchProvider` is registered, when `boot()` runs, then `SearchObserver` is registered in `ObserverRegistry` for all models implementing `Searchable`
- [ ] Given `SEARCH_QUEUE_SYNC=true`, when a model is updated, then the index sync is dispatched as a queued job rather than running inline

**Security Requirements**:
- [ ] `to_searchable_array()` must only include fields listed in `__searchable__` — no accidental leakage of sensitive columns
- [ ] Sensitive fields (passwords, tokens) must never appear in `__searchable__`; the framework must emit a warning if known sensitive column names are detected there

**Documentation Requirements**:
- [ ] Add `docs/site/docs/search.md` covering mixin usage and `__searchable__` configuration

**Requirement Refs**: Brainstorm design § Phase 2B
**Priority**: Must
**Complexity**: Medium
**Status**: Done

---

### Story 2: Fluent `SearchBuilder` API

**As a** framework user,
**I want** to call `Article.search("python")` and chain filters, ordering, and pagination,
**so that** I can construct search queries in the same style as the ORM `QueryBuilder` without raw driver calls.

**Acceptance Criteria**:
- [ ] Given `Article.search("python").limit(10).offset(20).get()`, when executed, then a list of `Article` instances (hydrated from DB by ID) is returned
- [ ] Given `.where("category", "news")`, when the query is executed, then the filter is forwarded to the engine as a driver-specific filter expression
- [ ] Given `.paginate(per_page=15, page=2)`, when executed, then a paginator compatible with the ORM paginator is returned
- [ ] Given `.keys()`, when executed, then only the document IDs (strings) are returned without DB hydration
- [ ] Given `.count()`, when executed, then the total number of matching documents is returned without fetching records
- [ ] Given `.raw()`, when executed, then the engine's native response object is returned (for driver-specific features)
- [ ] Given `Article.search("python")` with no engine configured, when executed, then a descriptive `SearchEngineNotConfigured` exception is raised (not a `NullPointerError`)

**Security Requirements**:
- [ ] Queries must be passed through as-is to the engine — no SQL concatenation, no injection vector via `SearchBuilder`

**Documentation Requirements**:
- [ ] Add `SearchBuilder` API reference to `docs/site/docs/search.md`

**Requirement Refs**: Brainstorm design § Phase 2B
**Priority**: Must
**Complexity**: Small
**Status**: Done

---

### Story 3: Multi-driver support via config

**As a** framework user,
**I want** to select the search backend (Meilisearch, Elasticsearch, database, null) via `SEARCH_DRIVER` config,
**so that** I can change infrastructure without touching application code.

**Acceptance Criteria**:
- [ ] Given `SEARCH_DRIVER=meilisearch` and `SEARCH_MEILISEARCH_URL` are set, when `SearchManager.create_driver()` is called, then a `MeilisearchEngine` instance connected to the configured URL is returned
- [ ] Given `SEARCH_DRIVER=elasticsearch` and `SEARCH_ELASTICSEARCH_URL` are set, when `SearchManager.create_driver()` is called, then an `ElasticsearchEngine` instance is returned
- [ ] Given `SEARCH_DRIVER=database`, when a search query runs, then it falls back to a SQL `ILIKE`/`MATCH` query against the model's table (best-effort, no ranking)
- [ ] Given `SEARCH_DRIVER=null`, when any `SearchEngine` method is called, then it succeeds silently (no-op) — for environments where search is explicitly disabled
- [ ] Given a custom driver is registered via `SearchManager.register_driver("my_driver", factory)`, when `SEARCH_DRIVER=my_driver` is set, then the custom engine is used
- [ ] Given an unknown `SEARCH_DRIVER` value, when the app boots, then `UnknownSearchDriverError` is raised with the driver name in the message

**Security Requirements**:
- [ ] Elasticsearch API keys / Meilisearch master keys must be loaded from environment variables only
- [ ] Database driver must use parameterized queries — no string-interpolated search terms into SQL

**Documentation Requirements**:
- [ ] Add driver configuration table to `docs/site/docs/search.md`

**Requirement Refs**: Brainstorm design § Phase 2B
**Priority**: Must
**Complexity**: Medium
**Status**: Done

---

### Story 4: Null and collection drivers for dev and testing

**As a** framework user,
**I want** a `null` driver (silent no-op) and a `collection` driver (in-memory, no external dependency),
**so that** I can develop and write tests without running a Meilisearch or Elasticsearch server.

**Acceptance Criteria**:
- [ ] Given `SEARCH_DRIVER=null`, when `upsert_documents`, `remove_documents`, and `search` are called, then they return empty/successful results without error and without any network call
- [ ] Given `SEARCH_DRIVER=collection`, when `upsert_documents([{"id": "1", "title": "Python"}])` is called, then the document is stored in memory
- [ ] Given the collection has documents, when `search("Python")` is called, then matching documents (case-insensitive substring) are returned as `SearchResult`
- [ ] Given the collection has documents, when `flush()` is called, then all documents are cleared
- [ ] Given a test uses `SearchFake`, when `fake.assert_indexed(article)` is called after a model save, then the assertion passes; `fake.assert_nothing_indexed()` passes when no models have been saved

**Security Requirements**:
- [ ] Collection driver must never persist data to disk — in-memory only

**Documentation Requirements**:
- [ ] Add testing section (fakes) to `docs/site/docs/search.md`

**Requirement Refs**: Brainstorm design § Phase 2B
**Priority**: Must
**Complexity**: Small
**Status**: Done

---

## Dependencies

- Depends on Epic 001 Story 1 (`context/` module) — queued sync jobs hydrate context
- Requires `arvel` core `data/` module (`ObserverRegistry`, `ArvelModel`) for observer registration
- Requires `arvel` core `queue/` module if `SEARCH_QUEUE_SYNC=true`
- Optional external deps: `meilisearch-python-sdk`, `elasticsearch[async]`

## Notes

- `Searchable.search()` must resolve `SearchEngine` from the DI container, not hardcode `NullEngine()` (bug fix from `arvel_old`)
- `SearchProvider.boot()` must register `SearchObserver` — was empty in `arvel_old` (bug fix)
- Database driver `search()` raising `NotImplementedError` is replaced with a working SQL fallback in this epic
- Hydrating model instances from search result IDs requires a DB round-trip — documented as a known performance trade-off
