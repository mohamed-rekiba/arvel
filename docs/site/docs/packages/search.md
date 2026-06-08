# arvel-search

<a name="introduction"></a>
## Introduction

`arvel-search` provides full-text search, modeled after Laravel Scout. Add `Searchable` to a model, declare which fields to index, and records sync to the configured backend automatically. Query with `Model.search("term")`.

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

Create/update/delete now sync to the search engine automatically (when an engine is bound).

Optional class attributes: `__search_index__` (index name; defaults from the table) and `__search_key__` (the document key; defaults to `id`). Override `to_searchable_array()` to control the indexed document.

<a name="searching"></a>
## Searching

```python
results = await Article.search("python").get()              # list[Article]
first = await Article.search("python").where("body", "x").first()
ids = await Article.search("python").keys()
total = await Article.search("python").count()
page = await Article.search("python").paginate(per_page=15, page=1)
```

The builder supports `where(column, value)`, `limit`, `offset`, and the terminal methods above. `where` filters keep their type on the server engines: numbers and booleans filter numeric/boolean fields (not stringified), and string values are quoted and escaped so a request-supplied value can't alter the filter expression.

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
| `SEARCH_SYNC_ON_SAVE` | `true` |
| `SEARCH_QUEUE_SYNC` | `false` |
| `SEARCH_MEILISEARCH_URL` | `http://localhost:7700` |
| `SEARCH_MEILISEARCH_KEY` | `""` |
| `SEARCH_ELASTICSEARCH_URL` | `http://localhost:9200` |
| `SEARCH_ELASTICSEARCH_KEY` | `""` |

Register a custom engine with `SearchManager.register_driver(name, factory)`.

<a name="bulk-reindexing"></a>
## Bulk (Re)indexing

```python
await Article.make_all_searchable()      # index every row
await Article.remove_all_from_search()   # clear the index
```

<a name="testing"></a>
## Testing

`Search.fake()` swaps in an assertable double:

```python
from arvel_search import Search

fake = Search.fake()
article = await Article.create(title="Hello", body="world")
fake.assert_indexed(article)
Search.restore()
```

<a name="gotchas"></a>
## Gotchas

- Querying with no engine bound raises `SearchEngineNotConfigured`; auto-sync is a no-op when no engine is bound.
- Declaring a sensitive-looking column in `__searchable__` triggers a runtime warning.
- The `database` driver searches live SQL — it doesn't build or maintain a separate index.
