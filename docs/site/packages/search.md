# arvel-search

<a name="introduction"></a>
## Introduction

`arvel-search` provides full-text search, modeled after Laravel Scout. Add `Searchable` to a model, declare which fields to index, and records sync to the configured backend automatically. Query with `Model.search("term")`.

<a name="a-quick-tour"></a>
## A Quick Tour

```bash
uv add "arvel[search]"
```

```python
# bootstrap/providers.py
from arvel_search import SearchServiceProvider

providers = [SearchServiceProvider]
```

```python
from arvel.database import Model, id_, string
from arvel_search import Searchable


class Article(Model, Searchable):
    __tablename__ = "articles"
    __searchable__ = ("title", "body")

    id: int = id_()
    title: str = string(200)
    body: str = string(2000)
```

```python
# create/update/delete auto-sync to the engine (when one is bound)
article = await Article.create(title="Hello Scout", body="world")

results = await Article.search("scout").get()
first = await Article.search("scout").where("body", "world").first()
page = await Article.search("scout").paginate(per_page=15, page=1)
```

No migrations — the package only adds indexing and query plumbing.

<a name="installation"></a>
## Installation

```bash
uv add "arvel[search]"
```

Register the provider:

```python
# bootstrap/providers.py
from arvel_search import SearchServiceProvider

providers = [SearchServiceProvider]
```

The provider registers `SearchConfig` and `SearchManager`, binds the `Search` facade, and registers the `SearchIndexJob` / `SearchRemoveJob` queue jobs. There are no migrations.

<a name="making-a-model-searchable"></a>
## Making a Model Searchable

Mix in `Searchable` and list the indexed fields in `__searchable__`:

```python
from arvel.database import Model, id_, string
from arvel_search import Searchable


class Article(Model, Searchable):
    __tablename__ = "articles"
    __searchable__ = ("title", "body")

    id: int = id_()
    title: str = string(200)
    body: str = string(2000)
```

Create/update/delete/restore now sync to the search engine automatically (when an engine is bound and `SEARCH_SYNC_ON_SAVE` is on).

Optional class attributes:

| Attribute | Default | Purpose |
|---|---|---|
| `__search_index__` | table name | Index name on the backend |
| `__search_key__` | `"id"` | Document key field |
| `__searchable__` | `()` | Columns sent to the index |

Override `to_searchable_array()` to control the indexed document — add computed fields, but keep it to non-sensitive data:

```python
class Article(Model, Searchable):
    __searchable__ = ("title", "body", "author_name")

    def to_searchable_array(self) -> dict[str, Any]:
        base = super().to_searchable_array()
        base["author_name"] = self.author.name if self.author else ""
        return base
```

Declaring a sensitive column in `__searchable__` triggers a runtime warning at class definition time (`password`, `token`, `api_key`, etc.).

<a name="searching"></a>
## Searching

```python
results = await Article.search("python").get()              # list[Article]
first = await Article.search("python").where("body", "x").first()
ids = await Article.search("python").keys()               # document keys only
total = await Article.search("python").count()
page = await Article.search("python").paginate(per_page=15, page=1)

raw = await Article.search("python").limit(10).offset(20).raw()  # SearchResult, no hydration
```

The builder supports `where(column, value)`, `limit`, `offset`, and the terminal methods above. `where` filters keep their type on the server engines: numbers and booleans filter numeric/boolean fields (not stringified), and string values are quoted and escaped so a request-supplied value can't alter the filter expression.

Chain filters for faceted admin search:

```python
published = await (
    Article.search(request.query_params.get("q", ""))
    .where("status", "published")
    .where("featured", True)
    .paginate(per_page=20)
)
```

<a name="manual-sync"></a>
## Manual Sync

When `SEARCH_SYNC_ON_SAVE=false`, or when you need to re-index outside the lifecycle hooks, call the instance and class helpers directly:

```python
await article.searchable()              # index (or re-index) this row now
await article.unsearchable()            # remove from the index

indexed = await Article.make_all_searchable()      # every row; returns count
await Article.remove_all_from_search()             # flush the whole index
```

These ignore `sync_on_save` — they talk to the engine whenever one is bound.

<a name="drivers"></a>
## Drivers

`SEARCH_DRIVER` picks the backend (default `database`):

| Driver | Behavior |
|---|---|
| `database` | `ILIKE` against the model's own table columns. Writes are no-ops — no separate index. Best for small tables / admin search. |
| `collection` | In-memory substring match. For tests and local dev. |
| `null` | Swallows writes; search returns nothing. |
| `meilisearch` | Talks to a Meilisearch server over HTTP. |
| `elasticsearch` | Talks to Elasticsearch over HTTP. |

Configuration (env, all `SEARCH_*`):

| Env var | Default |
|---|---|
| `SEARCH_DRIVER` | `database` |
| `SEARCH_INDEX_PREFIX` | `""` |
| `SEARCH_SYNC_ON_SAVE` | `true` |
| `SEARCH_QUEUE_SYNC` | `false` |
| `SEARCH_MEILISEARCH_URL` | `http://localhost:7700` |
| `SEARCH_MEILISEARCH_KEY` | `""` |
| `SEARCH_ELASTICSEARCH_URL` | `http://localhost:9200` |
| `SEARCH_ELASTICSEARCH_KEY` | `""` |

Register a custom engine with `SearchManager.register_driver(name, factory)`.

With `SEARCH_QUEUE_SYNC=true`, saves and deletes dispatch `SearchIndexJob` / `SearchRemoveJob` onto the queue instead of syncing inline — you'll need a worker running.

<a name="bulk-reindexing"></a>
## Bulk (Re)indexing

```python
count = await Article.make_all_searchable()      # index every row
await Article.remove_all_from_search()           # clear the index
```

For Meilisearch/Elasticsearch, run these after changing `__searchable__` or `to_searchable_array()` so the remote index matches your schema.

<a name="testing"></a>
## Testing

`Search.fake()` swaps in an assertable double:

```python
from arvel_search import Search

fake = Search.fake()
article = await Article.create(title="Hello", body="world")

fake.assert_indexed(article)
fake.assert_indexed_count(1)
fake.assert_not_indexed(other)
fake.assert_removed(deleted_article)
fake.assert_nothing_indexed()

Search.restore()   # always restore in teardown
```

While faked, lifecycle sync still runs — the fake records what would have been indexed.

<a name="gotchas"></a>
## Gotchas

- Querying with no engine bound raises `SearchEngineNotConfigured`; auto-sync is a no-op when no engine is bound.
- Declaring a sensitive-looking column in `__searchable__` triggers a runtime warning.
- The `database` driver searches live SQL — it doesn't build or maintain a separate index.
- `make_all_searchable()` loads every row into memory before upserting — fine for admin reindex, not for million-row tables without chunking at the app layer.
