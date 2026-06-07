# ADR-025 — `arvel-search`

**Status**: Accepted
**Date**: 2026-06-07 (first written down here; the package itself shipped earlier as pre-alpha)
**Scope**: All architectural decisions for the `arvel-search` package — package shape, the Scout-style `Searchable` mixin, the engine abstraction and the five built-in drivers, the fluent `SearchBuilder`, queued vs synchronous index sync, the test fake, and the deliberate non-management of indices.

## Why this is one ADR

`arvel-search` is a search abstraction for Arvel models. Six decisions define what it does (mixin + builder + 5 engines + queued sync + fake) and what it pointedly *doesn't* do (no index management, no analyzer config, no query DSL). They share infrastructure (the `Search` facade, the manager memoization, lifecycle hooks on the model) and read clearer end-to-end than as six separate files.

---

## § 1 — Scout-style mixin: `Searchable` + `__searchable__` declaration

### Context

There are three common shapes for "indexable model" APIs:

1. **Decorator** on the model class: `@indexable(fields=["title"])`.
2. **Method override**: `def to_index(self) -> dict: ...`.
3. **Mixin + class attribute**: `class Article(Model, Searchable): __searchable__ = ("title", "body")`.

Laravel's Scout uses option 3 (`use Searchable; public function toSearchableArray() { ... }`). It has the best ergonomics for the common case (declare two columns and you're done) while leaving the override path open for derived fields.

### Decision

`Searchable` is a mixin. The minimum declaration is one class attribute:

```python
class Article(Model, Searchable):
    __tablename__ = "articles"
    __searchable__ = ("title", "body")
```

Three optional class attributes:

- `__search_index__: str | None` — index name; defaults from `__tablename__`.
- `__search_key__: str` — document key; defaults to `id`.
- `to_searchable_array() -> dict[str, Any]` — overridable for derived fields.

`__init_subclass__` wires the lifecycle observers (see § 2) and **emits a warning at class-definition time** if the declared `__searchable__` set overlaps with a hardcoded list of sensitive field names (`password`, `password_hash`, `remember_token`, `secret`, `token`, `api_key`, `private_key`).

### Consequences

- The minimum viable indexing story is two lines added to the model.
- The sensitive-field warning catches an entire class of "we accidentally shipped passwords to Meilisearch" mistakes the first time the test suite imports the model.
- The override path (`to_searchable_array`) supports denormalisation: indexing a derived field, joining a related model, etc. The default body indexes the listed columns plus the key.
- `Model.search("python")` returns a typed `SearchBuilder[Self]` — the result list is `list[Article]`, not `list[Any]`.
- Subclasses of `Searchable` accumulate in a registry via `__init_subclass__`, so the install command can iterate every `Searchable` model to bulk re-index.

### Alternatives considered

- **Decorator**: works but composes poorly with model-DSL decorators (`@id_`, `@timestamps`).
- **Method-only**: forces every model to declare a method even when it just lists columns. Ceremony without value.

---

## § 2 — Index sync via Arvent lifecycle hooks: created/updated/restored/deleted

### Context

We need to keep the search index roughly in step with the database. Three options:

1. **Periodic re-index**: a cron job that re-indexes everything every N minutes. Simple, very stale.
2. **Database triggers**: forward changes via DB-level triggers. Engine-specific, hard to test, opaque to app developers.
3. **Application-level lifecycle hooks**: when the model fires `created`/`updated`/`deleted`, push the change to the engine.

### Decision

Option 3 — `Searchable.__init_subclass__` registers callbacks on `cls.on(...)`:

- `created`, `updated`, `restored` → `_on_save`: upsert the document via `engine.upsert_documents(...)`.
- `deleted` → `_on_delete`: remove via `engine.remove_documents(...)`.

The callbacks check three flags:

- `Search.is_faked()` short-circuits to the fake (see § 6) and *always* runs the sync.
- `manager.config.sync_on_save = False` lets apps disable hook-driven sync globally — useful for bulk import scripts that prefer a `make_all_searchable()` rebuild at the end.
- `manager.config.queue_sync` toggles between synchronous (in-process) and queued (via `SearchIndexJob` / `SearchRemoveJob`, see § 4).

### Consequences

- Indexing is automatic. The default app developer never calls `searchable()` — the mixin does it.
- The hook is the same surface used by `Auditable`, encryption, model events: one consistent observability model.
- Inserts and updates inside a transaction will sync the index *after* commit only if the engine call is queued (§ 4). Synchronous mode pushes to the engine inside the request, which means a long-tail engine (Elasticsearch over the network) directly raises request latency. Documented; queue mode is the production answer.
- A failed index sync in synchronous mode raises into the request handler. Apps that want best-effort indexing turn on queue mode and treat it as fire-and-forget.
- `restored` is forwarded as a save: re-indexed when soft-deletes are reversed.

### Alternatives considered

- **Periodic re-index**: too stale for the search-as-you-type case.
- **DB triggers**: opaque, brittle on migrations, no path to non-DB engines (Meilisearch, Elasticsearch) without bridging code anyway.

---

## § 3 — Engine abstraction with five built-in drivers: `null`, `collection`, `database`, `meilisearch`, `elasticsearch`

### Context

A search abstraction has to handle two extremes: a hosted Meilisearch in production, and a unit test that doesn't want to spin one up. Either we build one driver and require it everywhere, or we abstract and ship a few.

### Decision

`Engine` is an abstract base class with `upsert_documents`, `remove_documents`, `flush`, and `search` methods. Five concrete drivers:

| Driver | Behavior | Intended use |
|---|---|---|
| `null` | Swallows writes; search returns nothing | Disabling search without code changes |
| `collection` | In-memory substring match | Dev / test only |
| `database` | `ILIKE` against the model's own table; writes are no-ops | "Good enough" search without ops overhead |
| `meilisearch` | HTTP to a Meilisearch server | Production default |
| `elasticsearch` | HTTP to Elasticsearch | Production for ES-shop teams |

`SearchManager` is the registry. Engines are built lazily and **memoized once per driver name** for the manager's lifetime. Custom drivers register via `manager.register_driver(name, factory)`.

`SEARCH_DRIVER` config picks the active driver at runtime. The `database` driver was deliberately chosen as the default — apps with no Meilisearch / ES instance still get *some* search (slow, but real), and they don't need to add infra to stand up a project.

### Consequences

- Five drivers is a non-trivial maintenance surface, but each is small (~100-200 lines including the HTTP client). The manager keeps them isolated.
- The `database` driver only works when the searchable columns live on the same table. It's not a pretend-Meilisearch — it's a small-scale fallback that admits its limits.
- The `null` driver is the test default for "we don't care about search in this test path". Without it, every test that touches an indexed model would have to mount an engine.
- Custom drivers (Typesense, OpenSearch, Algolia) live in app code without forking the package — `manager.register_driver()` is the public extension point.
- Memoization means a single Meilisearch HTTP-client instance per process. If a test wants a fresh state, it calls `Search.fake()` (see § 6).

### Alternatives considered

- **One driver only** (Meilisearch): forces ops dependency for any app that wants search.
- **Plugin system with autodiscovery**: heavyweight for a small surface area. Direct registration is fine.

---

## § 4 — Optional queued sync via two job types

### Context

Synchronous index sync is fine for the database driver (writes are no-ops anyway) and acceptable for collection / null. For Meilisearch and Elasticsearch — both reachable only over HTTP — synchronous sync means every model save blocks on a network round-trip. That's the wrong default for production traffic.

### Decision

`SEARCH_QUEUE_SYNC=true` switches `Searchable._on_save` / `_on_delete` to dispatch `SearchIndexJob` / `SearchRemoveJob` to the queue. The jobs carry the model's import path (`__module__`, `__qualname__`) and a list of keys — **not the instance**. The worker re-imports the class, re-fetches the rows by key from the DB, and pushes the freshly-loaded documents to the engine.

```python
class SearchIndexJob(Job):
    queue: str = "search"
    model_module: str
    model_qualname: str
    keys: list[str]
```

### Consequences

- The instance can be GC'd or the request handler can return before the engine write happens.
- The worker reads the row at-of-handle time, not at-of-dispatch time. If two concurrent updates landed before the first job runs, the index reflects the latest committed state — never an out-of-order snapshot.
- The model's import path travels through the broker as plain strings. A class rename invalidates pending jobs (the worker raises `ImportError` / `AttributeError`). Documented; rename is a careful operation regardless.
- The `search` queue is dedicated by default — apps can route it to a queue-with-many-workers without competing with their main work.
- Fake mode (§ 6) ignores `queue_sync`: the fake captures every call directly, sync.

### Alternatives considered

- **Always queue**: rejected. The database driver has no engine to talk to; queueing a no-op is pure waste.
- **Carry the instance through the broker**: rejected. The queue serializer is JSON-shaped; instances aren't safe to round-trip and the result is stale anyway.

---

## § 5 — `SearchBuilder` is fluent, lazy, and forwards the query string verbatim

### Context

The query API has to satisfy three needs:

- **Ergonomic**: `Model.search("python").limit(10).get()`.
- **Hydrated**: returns model instances, not raw documents.
- **Engine-agnostic**: works the same for `database` / `meilisearch` / `elasticsearch` despite very different underlying query languages.

### Decision

`SearchBuilder[ModelT]` is a generic, fluent builder. Chainable methods (`where`, `limit`, `offset`) return `self`. Terminals (`get`, `first`, `keys`, `count`, `paginate`, `raw`) await on the engine and hydrate.

The query string is forwarded to the engine **verbatim** — no parsing, no escaping, no SQL concatenation. The package is not a query DSL.

`get()` calls `engine.search(...)`, then re-fetches the hits from the model's own DB by their keys. This guarantees hydrated objects reflect the live row, not the (potentially stale) indexed document. Order is preserved — the keys come back in relevance order from the engine and we hydrate in that order.

### Consequences

- Builders read like Eloquent / Arvent query builders elsewhere in the framework — same shape, same patterns, no new mental model.
- No injection vector. A user-supplied query string can't reach the SQL layer; it goes to the engine's HTTP endpoint as a JSON field. The DB hydration step uses parameterised `where_in` on keys.
- `paginate(per_page=15, page=1)` returns a `SearchPage` with `total`, `per_page`, `current_page` — same shape as the framework's other paginators (ADR-008).
- `raw()` exists for the rare case where a consumer wants engine highlights or facets that didn't justify first-class API surface.
- The two-step (engine → DB) is fine on a healthy index but leaks if many keys are in the index that no longer exist in the DB. Hydration silently drops them, which is the right behavior.

### Alternatives considered

- **Single-step**: return the engine documents directly. Rejected; consumers want the live model with its relations and methods.
- **Query DSL**: reject. Would need to translate to each engine's native language. Massive scope creep.

---

## § 6 — Test fake via `Search.fake()` / `Search.restore()`

### Context

Tests that exercise an indexed model shouldn't have to spin up Meilisearch, configure an in-memory engine, or stub the global facade by hand. They want an assertion API:

```python
Article.create(title="Hello", body="...")
fake.assert_indexed(article)
```

### Decision

`Search.fake()` swaps the active engine with a `SearchFake` that captures every `upsert_documents` / `remove_documents` / `flush` call and exposes assertion helpers (`assert_indexed`, `assert_unindexed`, `assert_nothing_indexed`, etc.). `Search.restore()` reinstates the original engine.

The fake **always runs the sync** — it ignores `sync_on_save` and `queue_sync` so tests don't have to flip flags.

### Consequences

- Tests touch the real lifecycle hook (so a missing observer registration is a test failure), but never the network or the in-memory collection engine.
- The pattern matches the framework's other fakes (Bus, Notification, Storage). One mental model.
- Forgetting `Search.restore()` leaks fake state across tests — the framework's `RefreshDatabase` test trait calls `restore` in tear-down to defend against this.

### Alternatives considered

- **Use the `collection` engine in tests**: works but doesn't give the assertion API, and tests would have to hand-roll "did this index call happen" checks.
- **Patch `engine.upsert_documents`**: brittle and requires a fresh patch in every test.

---

## § 7 — The package does *not* manage indices, mappings, or analyzers

### Context

Meilisearch and Elasticsearch both need indices to exist before documents are pushed. Some packages auto-create indices with default mappings on first use. The temptation: do that, save app developers the ops step.

### Decision

The package sends documents and queries only. It does **not** create indices, set mappings, configure analyzers, define synonyms, set ranking rules, or anything else that touches the engine's operational surface.

The README is explicit: "Make sure the index exists on the server first."

### Consequences

- Production indices stay under the team's control. The package can't accidentally clobber a hand-tuned mapping.
- Local development needs an extra step: `meilisearch` running, an index named after the table created. One-time, documented in the package's quick-start.
- If an index doesn't exist, the engine returns its own error and the request fails. We pass it through with a `SearchError`-shaped wrapper rather than swallowing it.
- We never carry a schema migration for the search engine — the framework's migration system stays focused on the relational DB.

### Alternatives considered

- **Auto-create indices**: rejected. Defaults that look right today drift from what production needs by year two.
- **Ship a `search:index` command** that creates indices from `__searchable__`: deferred. We can add it later as a thin CLI wrapper without changing the engine contract. Not built yet because the manual setup is one Meilisearch CLI call.

---

## Cross-references

- ADR-001 § 4 (single-`arvel` package + extras): `arvel[search]` follows the framework's package strategy.
- ADR-008 § 3 (lifecycle hooks): `Searchable` and `Auditable` use the same `cls.on(...)` surface.
- ADR-013 (Queue subsystem): § 4 dispatches `SearchIndexJob` / `SearchRemoveJob` through the same `Bus` facade.
- ADR-017 (Console / CLI): `Search.fake()` integrates with `RefreshDatabase` cleanup.
- ADR-023 (`arvel-audit`) § 2: `Auditable` uses the same lifecycle-event pattern; this package was modelled after that one.
- User-facing docs: `docs/site/docs/packages/search.md`.
