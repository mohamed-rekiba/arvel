# Search

Arvel does not ship a full-text search integration today. For applications that need search, the recommended approach is to use a dedicated search engine directly.

## Recommended engines

| Engine | When to use |
|---|---|
| **Postgres `tsvector`** | You already use Postgres and want zero new infrastructure |
| **Meilisearch** | Typo-tolerant, lightweight, self-hosted, great defaults |
| **Typesense** | Similar to Meilisearch with stronger schema typing |
| **OpenSearch / Elasticsearch** | Heavy-weight needs (analytics, log search, large corpora) |

## Postgres full-text search

Add a `tsvector` column maintained by Arvent:

```python
# database/migrations/...
def up(self) -> None:
    with self.create("articles") as t:
        t.id()
        t.string("title")
        t.text("body")
        t.column("search", "tsvector")
    self.raw("""
        CREATE INDEX articles_search_idx ON articles USING GIN (search);
        CREATE TRIGGER articles_search_trigger BEFORE INSERT OR UPDATE ON articles
        FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(search, 'pg_catalog.english', title, body);
    """)
```

Query it via the query builder:

```python
results = await Article.where_raw(
    "search @@ plainto_tsquery(:q)", {"q": user_query}
).limit(20).get()
```

## Meilisearch integration

Use the official `meilisearch-python` client and dispatch a [job](queues.md) to keep the index in sync with Arvent lifecycle events:

```python
@on_saved(Article)
async def index_article(article: Article) -> None:
    await Bus.dispatch(IndexArticle(article_id=article.id))
```

## Roadmap

A first-party `Searchable` mixin (Laravel Scout-style) is on the roadmap. For now, integrate directly.

## See also

- [Queues](queues.md) — keeping the search index in sync via jobs.
- [Events](events.md) — listening to model save events.
