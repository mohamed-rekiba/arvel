# arvel-search

<p>
<a href="https://pypi.org/project/arvel-search/">
    <img src="https://img.shields.io/pypi/v/arvel-search?color=%2334D058&label=pypi" alt="PyPI">
</a>
<img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License">
</p>

Scout-style full-text search for [Arvel](https://arvel.dev).

Add the `Searchable` mixin to a model, declare `__searchable__`, and records sync to your search
backend automatically on create / update / delete. Query with a fluent `Model.search("term")`
builder. Swap backends — Meilisearch, Elasticsearch, database (`ILIKE`), in-memory collection, or
null — entirely through config.

> **Status**: Pre-alpha.

---

**Documentation**: <a href="https://arvel.dev/packages/search" target="_blank">https://arvel.dev/packages/search</a>

---

## Install

```bash
uv add "arvel[search]"
# or: pip install arvel-search
```

Register the provider in `bootstrap/providers.py`:

```python
from arvel_search import SearchServiceProvider

providers = [
    # ...other providers...
    SearchServiceProvider,
]
```

The provider registers `SearchConfig` and `SearchManager`, binds the `Search` facade, and registers
the `SearchIndexJob` / `SearchRemoveJob` queue jobs. There are no migrations.

## Quick start

```python
from arvel.database import Model, id_, string
from arvel_search import Searchable


class Article(Model, Searchable):
    __tablename__ = "articles"
    __searchable__ = ("title", "body")

    id: int = id_()
    title: str = string(200)
    body: str = string(2000)


# Saving auto-indexes; deleting auto-removes (when an engine is bound).
article = await Article.create(title="Python tips", body="...")

# Fluent search, hydrated back into models.
results = await Article.search("python").limit(10).get()      # list[Article]
ids = await Article.search("python").keys()
total = await Article.search("python").count()
page = await Article.search("python").paginate(per_page=15, page=1)
```

The builder supports `where(column, value)`, `limit`, `offset`, plus the terminal methods
`get`, `first`, `keys`, `count`, and `paginate`.

Optional class attributes: `__search_index__` (index name; defaults from the table) and
`__search_key__` (document key; defaults to `id`). Override `to_searchable_array()` to control the
indexed document.

## Drivers

`SEARCH_DRIVER` picks the backend (default `database`):

| Driver | Behavior |
|---|---|
| `database` | `ILIKE` against the model's own table. Writes are no-ops — no separate index. |
| `collection` | In-memory substring match. Dev/test only. |
| `null` | Swallows writes; search returns nothing. |
| `meilisearch` | Talks to a Meilisearch server over HTTP. Set `SEARCH_MEILISEARCH_URL` / `_KEY`. |
| `elasticsearch` | Talks to Elasticsearch over HTTP. Set `SEARCH_ELASTICSEARCH_URL` / `_KEY`. |

> The Meilisearch and Elasticsearch drivers send documents and queries only — they don't create
> indices or mappings. Make sure the index exists on the server first.

## Testing

```python
from arvel_search import Search

fake = Search.fake()
article = await Article.create(title="Hello", body="...")
fake.assert_indexed(article)
Search.restore()
```

See the [full guide](https://arvel.dev/packages/search) for custom engines and queued sync.

## License

MIT — see [LICENSE](../../LICENSE).
