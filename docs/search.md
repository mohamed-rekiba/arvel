# Search

Full-text search over your models, kept in sync automatically. A **searchable** model is mirrored
into a search index every time it's saved and removed when it's deleted — so the index always
reflects your data, and you query it with one call instead of hand-rolling `LIKE` queries or
managing an external index yourself.

It's a model mixin plus a swappable **engine** (driver). The
built-in `array` engine keeps the index in memory — perfect for tests and small apps — and a
`meilisearch` engine (the `[search]` extra) backs production search.

## Making a model searchable

Mix in `Searchable` — **before** `Model`, so its save/delete hooks take effect:

```python
from arvel import Model
from arvel.search import Searchable

class Article(Searchable, Model):          # Searchable first (MRO)
    __fields__   = {"title": str, "body": str}
    __fillable__ = ["title", "body"]
```

That's it. Creating, updating, or deleting an `Article` now keeps the index in sync:

```python
article = await Article.create(title="Async Python", body="fast web apps")
hits = await Article.search("python")      # -> [<Article …>]  (hydrated models)
await article.delete()                     # removed from the index too
```

## Controlling what's indexed

By default the whole serialized model (`to_dict()`) is indexed under the table name. Override to
shape the document or rename the index:

```python
class Article(Searchable, Model):
    def to_searchable_array(self) -> dict:
        return {"title": self.title, "body": self.body}   # index only these

    @classmethod
    def searchable_as(cls) -> str:
        return "articles_v2"                              # custom index name
```

You can also drive the index by hand: `await article.searchable()` (index now) and
`await article.unsearchable()` (remove now).

## Engines

The engine is chosen by `config('search.driver')` (default `array`):

```python
# config/search.py
search = {
    "driver": "meilisearch",
    "meilisearch": {"url": "http://localhost:7700", "key": env("MEILISEARCH_KEY")},
}
```

| Driver | Backing | Use |
|--------|---------|-----|
| `array` | in-memory dict | default; tests, small apps |
| `meilisearch` | Meilisearch server | production (`uv add 'arvel[search]'`) |

Add your own with `app("search").extend("algolia", lambda app: MyEngine(...))` — any object
implementing the `SearchEngine` protocol (`index`/`delete`/`search`/`flush`).

!!! warning "Mix `Searchable` before `Model`"
    Python resolves methods left-to-right, so `class Article(Searchable, Model)` is required for the
    auto-sync hooks to run. `class Article(Model, Searchable)` would let `Model` shadow them.

## Common mistakes & gotchas

- **Mixing `Searchable` after `Model`.** As above — it *must* come first, or saves/deletes won't
  reach the index and your search silently goes stale.
- **Relying on the `array` engine in production.** It's in-memory and per-process: lost on restart,
  not shared across workers. Use Meilisearch (`arvel[search]`) for anything real.
- **Indexing everything.** The default indexes the whole model; override `to_searchable_array` to
  send only the fields you actually search, keeping the index lean and avoiding leaking hidden
  columns into it.
- **Forgetting an existing table needs backfilling.** Auto-sync only covers *future* saves — import
  current rows once (re-save them, or push each through `searchable()`) when you first add the mixin.

## How it works

`Searchable` hooks the model's lifecycle (the `_fire` override): a successful save calls
`searchable()` to push `to_searchable_array()` into the index under `searchable_as()`, and a delete
calls `unsearchable()` to remove it. `Model.search(query)` resolves the configured engine from the
`search` binding (a `SearchManager`, driver from `config('search.driver')`), runs the query, and
hydrates the matched records back into model instances. Engines are just objects implementing the
`SearchEngine` protocol, so swapping `array` ↔ `meilisearch` ↔ your own changes nothing at the call
site.

## See also

- [Database & ORM](database/index.md) — the models you make searchable, and Postgres
  [full-text search](database/json-search.md#full-text-search) for an in-database alternative.
