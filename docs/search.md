# Search

Full-text search over your models, kept in sync automatically. A **searchable** model is mirrored
into a search index every time it's saved and removed when it's deleted — so the index always
reflects your data, and you query it with a fluent builder instead of hand-rolling `LIKE` queries
or managing an external index yourself.

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
hits = await Article.search("python").get()   # -> [<Article …>]  (hydrated models)
await article.delete()                        # removed from the index too
```

## The fluent query builder

`Model.search(query)` returns a `SearchBuilder` — chain `where`/`order_by`/`take`, then run it with
`get`/`first`/`paginate`:

```python
page = await (
    Article.search("python")
    .where("published", True)          # equality filter
    .order_by("views", "desc")         # sort
    .paginate(per_page=10, page=1)     # a LengthAwarePaginator (DR-0022 shape)
)

first = await Article.search("python").first()      # one hydrated model, or None
top5  = await Article.search("python").take(5).get() # at most 5 hydrated models
```

Two escape hatches skip hydration:

- `await builder.keys()` — the matched records' raw index keys, unhydrated, in engine order.
- `await builder.raw()` — the engine's raw `SearchResult(hits, total)` payload.

Hydration runs a `whereIn(pk, keys)` fetch and re-orders the rows to match the engine's hit order
(the DB doesn't promise to preserve it). Soft-deleted models are excluded by default; call
`.with_trashed()` to include them.

### Declaring filterable/sortable fields (Meilisearch)

Meilisearch only honors `where`/`order_by` on fields declared as filterable/sortable index
settings. Declare them on the model — `scout:import` pushes them for you:

```python
class Article(Searchable, Model):
    @classmethod
    def searchable_filterable(cls) -> list[str]:
        return ["published"]

    @classmethod
    def searchable_sortable(cls) -> list[str]:
        return ["views"]
```

The `array` engine ignores these (it filters/sorts on any field, declared or not) — they only
matter once you're on `meilisearch`.

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

## Bulk import / flush (`scout:import` / `scout:flush`)

Auto-sync only covers *future* saves. Backfill an existing table, or rebuild after a driver
change, with the CLI — it chunks rows (so a large table doesn't load into memory at once) and
pushes the model's filterable/sortable settings first:

```bash
arvel scout:import app.models.article:Article   # dotted module:ClassName path
arvel scout:import Article                      # or the bare class name, inside a project
                                                 # (resolved from app/models, like the shell's autoload)
arvel scout:flush Article                       # empty the index
```

## Queued indexing (`search.queue`)

By default, a save/delete writes to the engine **inline**, on the request path. Set `search.queue`
to move that write off the request path instead:

```python
# config/search.py
search = {"driver": "array", "queue": True}
```

With `search.queue = True`, `Searchable` emits a `ModelIndexRequested(model_class, key, record)`
event through the events dispatcher instead of writing inline (`record` is `None` for a delete).
`SearchServiceProvider.boot()` auto-registers the shipped listener,
`arvel.search.listeners.handle_index_request`, whenever `search.queue` is on and an events
dispatcher is bound — so the seam works out of the box:

```python
# equivalent manual registration, e.g. in your own provider:
from arvel.search import ModelIndexRequested
from arvel.search.listeners import handle_index_request

app.make("events").listen(ModelIndexRequested, handle_index_request)
```

What this buys you is **decoupling**, not yet off-process execution: the save no longer calls the
search engine directly — it fires an event, and the shipped listener performs the write when that
event fires. But that listener still runs *inline*, in the same dispatch. To move the write onto a
background worker, register your own `ShouldQueue` listener that pushes a job instead of indexing
directly. `arvel.search` deliberately doesn't depend on `arvel.queue`, so whether and how to queue the
write stays your decision, not something the search layer forces.

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
implementing the `SearchEngine` protocol (`index`/`delete`/`search`/`flush`/`configure`). The
`meilisearch` engine runs every client call in a worker thread (the client is synchronous) and
waits for each write's server-side task to finish before returning — trading a little write
latency for read-your-writes consistency, since Meilisearch indexing is otherwise asynchronous.

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
- **Forgetting an existing table needs backfilling.** Auto-sync only covers *future* saves — run
  `scout:import` (or re-save the rows / push each through `searchable()`) once, when you first add
  the mixin.
- **`where`/`order_by` doing nothing on Meilisearch.** The field must be declared via
  `searchable_filterable`/`searchable_sortable` *and* re-imported (`scout:import`) so Meilisearch
  picks up the new index settings.

## How it works

`Searchable` hooks the model's lifecycle (the `_fire` override): a successful save calls
`searchable()` to push `to_searchable_array()` into the index under `searchable_as()`, and a delete
calls `unsearchable()` to remove it — inline by default, or via the `ModelIndexRequested` event when
`search.queue` is on. `Model.search(query)` returns a `SearchBuilder` that resolves the configured
engine from the `search` binding (a `SearchManager`, driver from `config('search.driver')`) lazily,
only once you run it (`get`/`first`/`paginate`/`keys`/`raw`), and hydrates matched records back into
model instances by primary key, preserving the engine's hit order. Engines are just objects
implementing the `SearchEngine` protocol, so swapping `array` ↔ `meilisearch` ↔ your own changes
nothing at the call site.

## See also

- [Database & ORM](database/index.md) — the models you make searchable, and Postgres
  [full-text search](database/json-search.md#full-text-search) for an in-database alternative.
