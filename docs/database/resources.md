# API Resources

A model's `to_dict()` is fine for a quick endpoint, but a public API usually needs to shape the
output differently from the storage schema: hide internal columns, rename keys, conditionally
include a relation only when it's eager-loaded, or add pagination metadata. `JsonResource` (Laravel
`eloquent-resources` parity) is that transform layer — declare the shape once, reuse it everywhere
the model is serialized.

## Defining a resource

```python
from typing import Any
from arvel.database import JsonResource

class PostResource(JsonResource[Post]):
    def to_array(self, request: Any | None = None) -> dict:
        return {
            "id": self.resource.id,
            "title": self.resource.title,
            "author": self.when_loaded("author", lambda a: {"name": a.name}),
        }
```

`self.resource` is the wrapped model (or any value — a resource doesn't require a `Model`). Return
a route handler a resource directly and the HTTP kernel serializes it for you:

```python
async def show(request, post: Post):
    return PostResource(post)          # -> {"data": {"id": ..., "title": ..., ...}}
```

## Conditional fields

- **`when(condition, value, default=MISSING)`** — `value` (or `value()` if callable) when
  `condition`, else `default`. A field left at the default `MISSING` is **stripped from the
  payload** entirely, not serialized as `null`.
- **`when_not_none(value)`** — `value` if not `None`, else `MISSING` (Laravel `whenNotNull`).
- **`when_loaded(relation, cb=None)`** — the eager-loaded relation's value (or `cb(value)` if
  given), or `MISSING` if `relation` wasn't eager-loaded (`Model.with_(...)`). This reads the
  model's loaded-relation bookkeeping directly — it never triggers a lazy query, so a resource is
  safe to serialize outside a request/DB context.
- **`merge_when(condition, mapping)`** — `mapping` when `condition`, else `{}`; spread it into
  `to_array`'s returned dict: `{**self.merge_when(is_admin, {"email": ...}), "id": ...}`.

```python
class PostResource(JsonResource[Post]):
    def to_array(self, request=None):
        return {
            "id": self.resource.id,
            "author": self.when_loaded("author", lambda a: {"name": a.name}),
            **self.merge_when(self.resource.body is not None, {"body": self.resource.body}),
        }

fetched = await Post.find(1)                 # "author" not eager-loaded
PostResource(fetched).to_payload()           # {"data": {"id": 1}}  — no "author" key at all

fetched = (await Post.with_("author").get())[0]
PostResource(fetched).to_payload()           # {"data": {"id": 1, "author": {"name": "Ada"}}}
```

## Wrapping and metadata

`to_payload(request=None)` is the final JSON-safe dict: `to_array()` with `MISSING` fields
stripped, wrapped under the class's `wrap` key (`"data"` by default — set `wrap = None` to disable
wrapping entirely; never double-wrapped), plus anything attached via `.additional(...)`:

```python
PostResource(post).additional({"version": "v1"}).to_payload()
# {"data": {...}, "version": "v1"}

class Unwrapped(JsonResource[Post]):
    wrap = None
    def to_array(self, request=None):
        return {"id": self.resource.id}

Unwrapped(post).to_payload()   # {"id": 1} — no "data" nesting
```

## Collections and pagination

`YourResource.collection(models)` returns a `ResourceCollection` — maps the resource over every
item, wrapped under the same key the singular resource would use:

```python
PostResource.collection(posts).to_payload()
# {"data": [{"id": 1, ...}, {"id": 2, ...}]}
```

Pass a paginator (`Builder.paginate()`/`simple_paginate()`) instead of a plain list and the
collection's `data` is still mapped through the resource, with `meta`/`links` alongside it —
Laravel's paginated-resource response shape (distinct from a bare paginator's own `to_dict()`,
which flattens those fields):

```python
page = await Post.paginate(per_page=10)
PostResource.collection(page).to_payload()
# {
#   "data": [{"id": 1, ...}, ...],
#   "links": {"first": "...", "last": "...", "prev": None, "next": "..."},
#   "meta": {"current_page": 1, "from": 1, "last_page": 3, "path": "...", "per_page": 10,
#            "to": 10, "total": 25},
# }
```

## Common mistakes & gotchas

- **`when_loaded` on a relation you forgot to eager-load.** It won't lazily fetch it — the field
  is just omitted. If it's always missing, check the handler actually called `.with_("relation")`.
- **Returning a resource from a non-HTTP context expecting a dict.** `JsonResource` itself isn't a
  dict; call `.to_payload()` explicitly outside the HTTP kernel's automatic conversion (e.g. inside
  a queued job or a CLI command).
- **A custom `wrap` clashing with `additional()` keys.** `additional({"data": ...})` would collide
  with the wrap key — pick a different top-level name for extra metadata.
