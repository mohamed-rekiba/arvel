# Pagination

Returning all rows to the client is rarely the right answer. Arvel's query builder and Arvent both ship with pagination helpers that produce predictable, JSON-friendly responses.

## Page-based pagination

The most common case — show page N of M with `per_page` items each:

```python
page = await User.order_by("-created_at").paginate(page=1, per_page=20)
```

`paginate` returns a `Paginator` object that knows how to render itself:

```python
{
    "data": [...],                # list of rows for the requested page
    "meta": {
        "current_page": 1,
        "per_page": 20,
        "total": 137,
        "last_page": 7,
        "from": 1,
        "to": 20
    },
    "links": {
        "first": 1,
        "prev": null,
        "next": 2,
        "last": 7
    }
}
```

Use it directly as a JSON response:

```python
@Route.get("/users")
async def index(page: int = 1, per_page: int = 20) -> dict:
    paginator = await User.paginate(page=page, per_page=per_page)
    return paginator.to_dict()
```

### HATEOAS-style URL links

Pass `base_url` to `to_dict()` (or call `links()` directly) and the `links` block
holds fully-built URLs instead of page numbers. Filters and sorts survive
pagination — pass them through `query` and they're merged into every URL:

```python
@Route.get("/users")
async def index(request: Request, page: int = 1, per_page: int = 20) -> dict:
    paginator = await User.paginate(page=page, per_page=per_page)
    return paginator.to_dict(
        base_url=str(request.url_for("index")),
        query={"sort": request.query_params.get("sort", "-created_at")},
    )
```

The payload's `links` block now looks like:

```json
{
    "first": "https://api.example.com/users?sort=-created_at&page=1",
    "prev":  null,
    "next":  "https://api.example.com/users?sort=-created_at&page=2",
    "last":  "https://api.example.com/users?sort=-created_at&page=7"
}
```

`prev` and `next` are `null` on the first and last page respectively. The
paginator always owns the `page` query key — if a caller passes one in `query`,
it's overwritten so URLs never end up with duplicate `page=` entries.

Need just the URLs without the full envelope? Call `links()` directly:

```python
urls = paginator.links(str(request.url_for("index")), query={"sort": "asc"})
# {"first": "...?sort=asc&page=1", "prev": None, "next": "...&page=2", "last": "...&page=7"}
```

### Automatic page resolution

`paginate` and `simple_paginate` resolve the page from the request when you don't pass one. The
`ObservabilityMiddleware` records the request path and query, so `?page=3` is picked up:

```python
@Route.get("/users")
async def index() -> dict:
    # page comes from ?page=N (default 1); per_page is yours to control
    return (await User.paginate(per_page=20)).to_response()

# Custom query key:
await User.paginate(per_page=20, page_name="p")   # reads ?p=N
```

### Laravel-style flat envelope

`to_response()` emits Laravel's flat `LengthAwarePaginator` shape — drop-in for clients ported
from Laravel:

```python
page = await User.paginate(per_page=20)
page.to_response()
# {
#   "current_page": 2, "data": [...], "first_page_url": "/users?page=1",
#   "from": 21, "last_page": 7, "last_page_url": "/users?page=7",
#   "links": [{"url": "...", "label": "&laquo; Previous", "active": false}, ...],
#   "next_page_url": "/users?page=3", "path": "/users", "per_page": 20,
#   "prev_page_url": "/users?page=1", "to": 40, "total": 137
# }
```

The `links` array is the windowed page list. Control how many pages flank the current one with
`on_each_side` (default 3) on the `Paginator`.

### Preserving query parameters

Chainable, immutable helpers carry filters/sorts onto every generated URL:

```python
page = await Product.where("active", True).paginate(per_page=20)

page.appends({"sort": "-price"}).to_response()    # every URL gets ?sort=-price
page.with_query_string().to_response()            # carry the whole request query (minus page)
page.fragment("results").to_response()            # every URL ends with #results
```

## Cursor-based pagination

For large datasets and infinite-scroll UIs, cursor pagination scales better than page-based — there's no `OFFSET`, so deep pages stay fast regardless of how far in you are:

```python
cursor = request.query_params.get("cursor")   # None on the first request

page = await Post.cursor_paginate(per_page=20, cursor=cursor)
```

The result is a `CursorPaginator[T]` — bidirectional, so you can walk forward **and** back:

```python
page.items          # Collection[Post] — the current page
page.per_page       # 20
page.next_cursor    # str | None — None at the end
page.prev_cursor    # str | None — None on the first page
```

The cursor also resolves from the request automatically (`?cursor=...`), so you can skip
passing it:

```python
@router.get("/posts")
async def list_posts() -> dict:
    page = await Post.cursor_paginate(per_page=20)   # cursor read from ?cursor=
    return page.to_response()
    # {"data": [...], "path": "/posts", "per_page": 20,
    #  "next_cursor": "...", "prev_cursor": null,
    #  "next_page_url": "/posts?cursor=...", "prev_page_url": null}
```

On the client, pass `next_cursor` as `?cursor=` to advance, or `prev_cursor` to go back. When a cursor is `null`, you've hit that end.

Cursor values are opaque base64 tokens encoding the boundary row's keyset plus a direction flag. Don't parse or construct them manually. A malformed or tampered cursor raises `InvalidCursorError` (from `arvel.database.exceptions`) instead of silently returning the first page — catch it at the route boundary and return a `400` if you want a friendlier response.

## Simple pagination

When you don't care about the total count (and don't want the `COUNT(*)` query overhead), use `simple_paginate`:

```python
page = await Post.simple_paginate(page=1, per_page=20)
```

Returns the rows plus `has_more` — no `total`, no `last_page`. Useful when totals don't fit in memory or the count is expensive.

`SimplePaginator.links(base_url)` returns just `{prev, next}` — there's no
`first`/`last` because total is unknown:

```python
page.links("https://api.example.com/feed")
# {"prev": "https://api.example.com/feed?page=1", "next": "https://api.example.com/feed?page=3"}
```

The same `to_dict(base_url=..., query=...)` toggle works on `SimplePaginator`.

## Customizing the response shape

The defaults above match a common convention, but you can tailor the shape per endpoint with `JsonResource`:

```python
from arvel.http import JsonResource


class UserResource(JsonResource[User]):
    def transform(self, user: User) -> dict:
        return {"id": user.id, "name": user.name, "email": user.email}


@Route.get("/users")
async def index(page: int = 1) -> dict:
    paginator = await User.paginate(page=page, per_page=20)
    return UserResource.from_paginator(paginator).to_dict()
```

`from_paginator(...)` keeps the meta + links and runs `transform()` on each row in `data`.

## Choosing a strategy

| Strategy | Use when | Trade-off |
|---|---|---|
| `paginate` | You need total count and last-page links | `COUNT(*)` query overhead |
| `simple_paginate` | You don't need totals (e.g., "load more" UI) | No total, but cheap and predictable |
| `cursor_paginate` | Large datasets, infinite scroll, deep pages | Cursors are opaque; harder to "jump to page X" |

## Where to next?

- [Query Builder](queries.md) — composing the underlying queries.
- [API Resources](arvent-resources.md) — shaping the response.
