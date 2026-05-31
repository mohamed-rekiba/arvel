# arvel-search

Scout-style full-text search for [Arvel](https://github.com/mohamed-rekiba/arvel).

Add the `Searchable` mixin to a model, declare `__searchable__`, and records sync
to your search backend automatically on create/update/delete. Query with a fluent
`Model.search("term")` builder. Swap backends — Meilisearch, Elasticsearch,
database (SQL `ILIKE`), in-memory collection, or null — entirely through config.

## Install

```bash
uv add arvel-search
```

## Quick start

```python
from arvel.database import Model
from arvel_search import Searchable


class Article(Model, Searchable):
    __tablename__ = "articles"
    __searchable__ = ("title", "body")

    title: str
    body: str


# Saving auto-indexes; deleting auto-removes.
article = await Article.create(title="Python tips", body="...")

# Fluent search, hydrated back into models.
results = await Article.search("python").limit(10).get()
```

## Drivers

Set `SEARCH_DRIVER` to one of:

| Driver | Notes |
|---|---|
| `database` (default) | SQL `ILIKE` against the model's table. No server. |
| `meilisearch` | REST over httpx. Set `SEARCH_MEILISEARCH_URL` / `SEARCH_MEILISEARCH_KEY`. |
| `elasticsearch` | Bulk + `_search` REST. Set `SEARCH_ELASTICSEARCH_URL` / `SEARCH_ELASTICSEARCH_KEY`. |
| `collection` | In-memory substring match. Dev/test only. |
| `null` | No-op. Disables search without removing `Searchable`. |

## Testing

```python
from arvel_search import Search

fake = Search.fake()
await Article.create(title="Hello", body="...")
fake.assert_indexed(article)
fake.assert_nothing_indexed()  # when no saves happened
```

See the full guide at `docs/site/docs/search.md`.
