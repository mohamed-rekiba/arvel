# Full-Text Search

`arvel-search` brings Scout-style full-text search to Arvel. Add the `Searchable`
mixin to a model, declare which columns are indexable, and records sync to your
search backend automatically on create, update, and delete. Query with a fluent
`Model.search("term")` builder. Swap backends — Meilisearch, Elasticsearch,
database (`ILIKE`), in-memory collection, or null — entirely through config, with
no application code changes.

`arvel-search` is a separate workspace package. Install it through the `search`
extra:

```bash
uv add "arvel[search]"
```

## The `Searchable` mixin

Add `Searchable` to a model and declare `__searchable__`:

```python
from arvel.database import Model
from arvel_search import Searchable
from sqlalchemy.orm import Mapped, mapped_column


class Article(Model, Searchable):
    __tablename__ = "articles"
    __searchable__ = ("title", "body")

    title: Mapped[str] = mapped_column(nullable=False)
    body: Mapped[str] = mapped_column(nullable=False)
    secret_notes: Mapped[str] = mapped_column(nullable=False)  # never indexed
```

That's it — no observer code. Saving an `Article` indexes it; updating re-indexes;
deleting removes it. Only the columns in `__searchable__` are sent to the backend,
so columns like `secret_notes` never leave your database.

| Hook | Behavior |
|---|---|
| `__searchable__` | Tuple/list of column names to index. The primary key is always included. |
| `__search_index__` | Override the index name. Defaults to `__tablename__`. |
| `__search_key__` | Override the key column. Defaults to `"id"`. |
| `to_searchable_array()` | Override to compute derived/denormalized fields. Keep it non-sensitive. |

If a known-sensitive column (`password`, `token`, `secret`, …) appears in
`__searchable__`, the framework emits a warning at class-definition time — these
would otherwise be shipped to the backend in plaintext.

### Manual and bulk sync

```python
await article.searchable()          # index one record now
await article.unsearchable()        # remove one record now
await Article.make_all_searchable()  # backfill the whole table
await Article.remove_all_from_search()  # flush the index
```

### Queued sync

Set `SEARCH_QUEUE_SYNC=true` to push index updates onto the queue instead of
running them inline on save. The model's keys are queued; a worker re-loads the
rows from the database (so the index reflects committed state) and indexes them.

## The `SearchBuilder`

`Model.search("term")` returns a chainable builder. Nothing hits the backend
until you await a terminal.

```python
# Hydrate hits back into model instances (preserves relevance order).
results = await Article.search("python").limit(10).offset(20).get()

# Filter on an indexed field.
news = await Article.search("python").where("category", "news").get()

# Just the document keys — no DB round-trip.
ids = await Article.search("python").keys()

# Total match count, no hydration.
total = await Article.search("python").count()

# The engine's native response, for driver-specific features.
raw = await Article.search("python").raw()

# Offset pagination (1-based page).
page = await Article.search("python").paginate(per_page=15, page=2)
page.items, page.total, page.last_page, page.has_more
```

The query string is forwarded to the engine verbatim — there's no SQL
concatenation, so `SearchBuilder` is not an injection vector. The database driver
binds the term as a parameter.

If you call a terminal with no engine configured, you get a descriptive
`SearchEngineNotConfigured` (not an obscure attribute error).

## Drivers

Select the backend with `SEARCH_DRIVER`:

| Driver | When to use | Config |
|---|---|---|
| `database` (default) | Small tables, admin search. SQL `ILIKE` against the model's table — no server, no ranking. | — |
| `meilisearch` | Production full-text with ranking and typo tolerance. | `SEARCH_MEILISEARCH_URL`, `SEARCH_MEILISEARCH_KEY` |
| `elasticsearch` | Large-scale search and analytics. | `SEARCH_ELASTICSEARCH_URL`, `SEARCH_ELASTICSEARCH_KEY` |
| `collection` | Local dev / tests. In-memory, case-insensitive substring match. Never persisted. | — |
| `null` | Disable search without removing `Searchable`. All operations no-op. | — |

| Env var | Purpose |
|---|---|
| `SEARCH_DRIVER` | Active driver (default `database`) |
| `SEARCH_SYNC_ON_SAVE` | Auto-sync on lifecycle events (default `true`) |
| `SEARCH_QUEUE_SYNC` | Queue index sync instead of inline (default `false`) |
| `SEARCH_MEILISEARCH_URL` / `SEARCH_MEILISEARCH_KEY` | Meilisearch host + master key |
| `SEARCH_ELASTICSEARCH_URL` / `SEARCH_ELASTICSEARCH_KEY` | Elasticsearch host + API key |

Backend credentials are read from the environment only and held as `SecretStr`.
An unknown `SEARCH_DRIVER` raises `UnknownSearchDriverError` naming the bad value.

The Meilisearch and Elasticsearch drivers talk to their REST APIs directly over
`httpx` — no heavy SDK dependency.

### Custom drivers

```python
from arvel_search import SearchManager
from arvel_search.engine import Engine

manager.register_driver("my_engine", lambda: MyEngine(...))
# Then set SEARCH_DRIVER=my_engine.
```

## Testing with `SearchFake`

`Search.fake()` swaps the active engine for an in-memory fake that records every
index write, so you can assert on sync behavior without a running server:

```python
from arvel_search import Search

def test_publishing_indexes_the_article():
    fake = Search.fake()

    article = await Article.create(title="Hello", body="world")
    fake.assert_indexed(article)

    await article.delete()
    fake.assert_removed(article)

    fake.assert_indexed_count(1)
```

The fake also behaves like the collection driver for reads, so
`await Article.search("hello").keys()` works in tests too. Call `Search.restore()`
to route back to the real engine.

## Service provider

Register `SearchServiceProvider` in your app's provider list. It binds the
`SearchConfig` and `SearchManager`, points the `Search` facade at the manager,
and registers the queued-sync jobs. `Searchable` models wire their own lifecycle
hooks at class-definition time, so there's nothing to register per model.
