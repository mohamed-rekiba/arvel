# Pagination

When a query returns more rows than you want on one screen, **paginate** it. arvel's
paginators split the results into pages, build the page URLs for you (reading the current
page from the request's `?page=`), serialize straight to JSON for an API, and render a
ready-made HTML page-link bar for a server-rendered view — one surface that covers both.

## The quick version

```python
from app.models.user import User

async def index(request):
    users = await User.paginate(per_page=15)   # page comes from ?page= (defaults to 1)
    return users                                # in an API: auto-serialized to JSON (see below)
```

`paginate()` returns a **paginator**, not a list. It's iterable, so you can loop it
directly, and it carries everything you need to render page links.

```python
for user in users:        # iterate the rows on this page
    print(user.name)

users.total()         # 57   — grand total across all pages
users.current_page()  # 1
users.last_page()      # 4    — ceil(57 / 15)
users.per_page()       # 15
users.count()          # 15   — rows on *this* page
users.first_item()     # 1    — 1-based index of the first row on this page
users.last_item()      # 15
users.has_more_pages() # True
users.items()          # a Collection of the rows on this page
```

## Two kinds of paginator

| Method | Returns | Runs a `COUNT`? | Use when |
|---|---|---|---|
| `paginate(per_page)` | `LengthAwarePaginator` | Yes | you want page **numbers** (1 2 3 … 9) and a total |
| `simple_paginate(per_page)` | `Paginator` | No | you only need **Previous / Next** (cheaper on huge tables) |

`simple_paginate()` skips the `COUNT` query — it fetches one extra row to find out whether
a *next* page exists, and that's all it knows. So it has `has_more_pages()` and
`next_page_url()`, but no `total()` or `last_page()`.

```python
users = await User.where(active=True).order_by("name").simple_paginate(per_page=20)
users.has_more_pages()   # True/False
users.next_page_url()    # "/users?page=2" or None
```

Both work on any query builder chain — `where`, `order_by`, scopes, joins, all of it.

## In an API: JSON

Return a paginator straight from a JSON handler and arvel serializes it to the
paginator shape automatically:

```python
from arvel import Route

async def users_index(request):
    return await User.paginate(per_page=2)

Route.get("/api/users", users_index, name="api.users")
```

```jsonc
// GET /api/users?page=1
{
  "current_page": 1,
  "data": [ { "id": 1, "name": "Ada" }, { "id": 2, "name": "Linus" } ],
  "first_page_url": "/api/users?page=1",
  "from": 1,
  "last_page": 3,
  "last_page_url": "/api/users?page=3",
  "links": [
    { "url": null,                "label": "&laquo; Previous", "active": false },
    { "url": "/api/users?page=1", "label": "1",                "active": true  },
    { "url": "/api/users?page=2", "label": "2",                "active": false },
    { "url": "/api/users?page=3", "label": "3",                "active": false },
    { "url": "/api/users?page=2", "label": "Next &raquo;",     "active": false }
  ],
  "next_page_url": "/api/users?page=2",
  "path": "/api/users",
  "per_page": 2,
  "prev_page_url": null,
  "to": 2,
  "total": 5
}
```

The rows in `data` are serialized with each model's `to_dict()` (so `hidden`/`visible`
and date casts are honored — a date column comes back as an ISO-8601 string). The page
URLs are built from the **current request path** and `?page=`, so the client can follow
`next_page_url` without you constructing anything.

`simple_paginate()` returns the same shape minus `total`, `last_page`, `last_page_url`
and the numbered `links` (it only knows prev/next).

## In a view: HTML links

In a server-rendered page, call `links()` to render a styled page-link bar (Tailwind
classes, accessible markup), then drop it into your template:

```python
from arvel import view

async def users_page(request):
    users = await User.paginate(per_page=15)
    links = await users.links()                       # -> safe HTML
    return await view("users.index", {
        "users": users.items().all(),
        "links": links,
    }).to_response()
```

```html
<!-- resources/views/users/index.html -->
<ul>
  {% for user in users %}<li>{{ user.name }}</li>{% endfor %}
</ul>

{{ links }}
```

`links()` renders nothing when there's only a single page, so the bar simply disappears
when it isn't needed. `simple_paginate()` renders a Previous/Next bar instead.

### Controlling the page-number window

By default the bar shows 3 page numbers on each side of the current page, collapsing the
rest into `…` separators. Tune it with `on_each_side`:

```python
links = await users.on_each_side(2).links()
```

### Using your own template

The bar is rendered from a template in the `pagination` view namespace
(`pagination::default.html` for `paginate()`, `pagination::simple.html` for
`simple_paginate()`). Pass your own template name to override it:

```python
links = await users.links("pagination::custom.html")
```

Your template receives the paginator as `paginator`, so you can use
`paginator.elements()` (the page-number window — a list of `{page: url}` bands separated
by `"..."` strings), `paginator.previous_page_url()`, `paginator.next_page_url()`, and the
accessors above.

## Page URLs

The current page is read from the request's `?page=` query parameter and the path from the
request itself — so the same handler works on `/users`, `/users?page=2`, etc. with no extra
wiring. Outside a request (a script, a test) it falls back to page `1` and path `/`.

Add your own query string to every page link with `append`/`appends`, carry the *current*
query string through with `with_query_string()`, and add a URL `#fragment` with `fragment`:

```python
users = await User.paginate(per_page=15)
users.append("sort", "name")          # every page URL gets &sort=name
users.appends({"team": 4, "q": "ada"})
users.with_query_string()              # carry through the request's other query params
users.fragment("results")             # ...#results

users.url(2)            # build a specific page's URL yourself
users.next_page_url()   # "/users?page=2&sort=name#results"
```

## Picking the page explicitly

Pass `page=` to override the request-derived page (handy in scripts or tests):

```python
page2 = await User.paginate(per_page=15, page=2)
```

## Importing the paginators directly

You rarely construct these by hand — `paginate()` does it — but they're exported if you
need to paginate an in-memory list:

```python
from arvel import LengthAwarePaginator, Paginator

paginator = LengthAwarePaginator(items, total=100, per_page=15, current_page=1, path="/things")
```

## Common mistakes & gotchas

- **Treating a paginator like a list.** `paginate()` returns a paginator, not the rows. Iterate it
  directly, or call `.items()` for the `Collection` of this page's rows.
- **`total()` on a simple paginator.** `simple_paginate()` never runs a `COUNT`, so it has no
  `total()`/`last_page()` — only prev/next. Use `paginate()` when you need page numbers.
- **A `COUNT` you didn't want.** On a huge, frequently-written table, the `COUNT` behind `paginate()`
  is the expensive part. Prefer `simple_paginate()` when Previous/Next is enough.
- **Losing filters across pages.** The generated URLs carry only `?page=`. Call `with_query_string()`
  (or `append`/`appends`) so a page link keeps the current sort/search params.

## See also

- [Queries](database/queries.md) — `paginate()` / `simple_paginate()` on the query builder.
- [Transactions & Streaming](database/transactions.md) — `chunk_by_id`/`cursor` for processing (not
  displaying) a large result set.
- [Views](views.md) — rendering templates and registering view namespaces.
