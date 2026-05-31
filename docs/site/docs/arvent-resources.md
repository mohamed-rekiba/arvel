# API Resources

When building APIs, you often want to transform models — strip private fields, rename keys, add computed properties — before sending them to the client. Arvel calls this transformation layer **JSON Resources**.

## Defining a resource

```python
# app/Http/Resources/UserResource.py
from arvel.http import JsonResource


class UserResource(JsonResource):
    async def to_dict(self, request) -> dict:
        return {
            "id": self.resource.id,
            "name": self.resource.name,
            "email": self.resource.email if request.user.is_admin else None,
            "joined_at": self.resource.created_at.isoformat(),
        }
```

`self.resource` is the underlying model. The resource has full access to the request (for permission-aware shaping) and other facades.

## Returning a single resource

```python
@Route.get("/users/{user_id}")
async def show(user_id: int, request: Request) -> Response:
    user = await User.find_or_fail(user_id)
    return UserResource(user).response(request)
```

## Collections

```python
@Route.get("/users")
async def index(request: Request) -> Response:
    users = await User.limit(20).get()
    return UserResource.collection(users).response(request)
```

The collection wrapper iterates the models and applies the resource to each.

### Paginated collections

`collection()` also accepts any of Arvel's paginators — `Paginator`,
`SimplePaginator`, or `CursorPaginator`. When you hand it a paginator, the
envelope changes from `{data: [...]}` to the full
`{data: [...], meta: {...}, links: {...}}` shape, with each item still
transformed through your resource class:

```python
@Route.get("/users")
async def index(request: Request) -> Response:
    page = await User.paginate(per_page=20)
    return UserResource.collection(page).response(request)
```

The resource collection introspects `request` to build URL-style links:

- `request.url.{scheme,netloc,path}` becomes the base URL.
- `request.query_params` is merged into every link so filters and sort
  flags survive pagination. `page` and `cursor` are stripped — those keys
  belong to the paginator.
- If the request doesn't expose those attributes (e.g. an ad-hoc test
  dummy), `links` falls back to integer page numbers.

Example response for `GET /api/users?sort=name&page=3` against a
`Paginator`:

```json
{
  "data": [
    {"id": 41, "name": "Alice"},
    {"id": 42, "name": "Bob"}
  ],
  "meta": {
    "total": 42,
    "per_page": 2,
    "current_page": 3,
    "last_page": 21,
    "from": 5,
    "to": 6
  },
  "links": {
    "first": "https://api.example.com/api/users?sort=name&page=1",
    "prev":  "https://api.example.com/api/users?sort=name&page=2",
    "next":  "https://api.example.com/api/users?sort=name&page=4",
    "last":  "https://api.example.com/api/users?sort=name&page=21"
  }
}
```

`SimplePaginator` returns only `prev`/`next` (no total, no `last`).
`CursorPaginator` returns a single `next` link whose URL embeds the
opaque cursor as `?cursor=<token>`.

The HTTP layer never imports the paginator types — it accepts anything
that quacks like one via the public `arvel.http.Paginatable` Protocol.
That keeps `arvel.http` and `arvel.database` decoupled (ADR-016).

### Extra root keys with `.additional({...})`

Merge extra keys into the root response envelope without subclassing:

```python
@Route.get("/users")
async def index(request: Request) -> Response:
    page = await User.paginate(per_page=20)
    return (
        UserResource.collection(page)
        .additional({"meta": {"trace_id": request.state.trace_id}})
        .response(request)
    )
```

The extras merge AFTER the default envelope (or the paginator's
`{data, meta, links}` block) is built, so caller keys win on clash —
useful for stamping correlation IDs, feature flags, or per-request
debug metadata onto an existing response shape.

`.additional({...})` also exists on `JsonResource` itself for single-
resource responses:

```python
return UserResource(user).additional({"links": {"self": str(request.url)}}).response(request)
```

Both `JsonResource.additional` and `ResourceCollection.additional`
return `Self` so the call chains naturally.

## Wrapping with metadata

```python
class UserResource(JsonResource):
    wrap = "user"   # → {"user": {...}}


class UserCollection(JsonResourceCollection):
    wrap = "users"

    async def with_metadata(self, request) -> dict:
        return {"total": await User.count()}
```

## Conditional attributes

```python
async def to_dict(self, request) -> dict:
    return {
        "id": self.resource.id,
        "name": self.resource.name,
        **self.when(request.user.is_admin, {"email": self.resource.email}),
        **(await self.when_loaded("posts", lambda: PostResource.collection(self.resource.posts).to_dict(request))),
    }
```

`when` and `when_loaded` keep conditional fields readable.

## See also

- [Responses](responses.md) — the underlying response objects.
- [ORM → Serialization](arvent-serialization.md) — for simpler `to_dict()` shaping on the model itself.
- [ORM → Relationships](arvent-relationships.md) — eager loading before resource transformation.
