# API Resources

<a name="introduction"></a>
## Introduction

When building an API, you often need a transformation layer that sits between your ORM models and the JSON responses actually returned to your application's users. For example, you may wish to display certain attributes for a subset of users and not others, or you may wish to always include certain relationships in the JSON representation of your models. Resource classes let you expressively and easily transform your models into JSON.

You can always return a plain `dict`, `list`, or Pydantic model from a handler and let FastAPI serialize it. Resources are for when you want a *reusable, explicit* mapping from a model to its JSON shape, kept out of your handlers.

<a name="generating-resources"></a>
## Generating Resources

Scaffold a resource with the `make:resource` command:

```bash
arvel make:resource UserResource
```

<a name="writing-resources"></a>
## Writing Resources

A resource class represents a single model that needs to be transformed into a JSON structure. Subclass `JsonResource[T]`, where `T` is the model type the resource wraps. The wrapped model is available as `self.resource`.

<a name="the-to-dict-method"></a>
### The to_dict Method

Every resource implements a single `to_dict` method, which returns the dictionary of attributes that should be converted to JSON when the resource is returned from a route. The model is accessible via `self.resource`:

```python
from typing import Any

from arvel.http.resources import JsonResource
from app.models.user import User


class UserResource(JsonResource[User]):
    def to_dict(self, request: Any) -> dict[str, Any]:
        return {
            "id": self.resource.id,
            "name": self.resource.name,
            "email": self.resource.email,
            "created_at": self.resource.created_at,
        }
```

<a name="returning-a-resource"></a>
### Returning a Resource

Once a resource is defined, it may be returned from a route. Call `response(request)` to produce the JSON response:

```python
from arvel import Route
from starlette.requests import Request
from app.models.user import User


@Route.get("/api/users/{user}", name="users.show")
async def show(user: User, request: Request):
    return UserResource(user).response(request)
```

The route and collection handlers below assume the same `Route`, `Request`, and `User` imports.

`response()` accepts an optional status code and headers:

```python
return UserResource(user).response(request, status_code=201, headers={"X-Foo": "bar"})
```

If you'd rather get the plain dictionary (for example, to nest it inside a larger structure), call `to_dict(request)` directly and let FastAPI serialize the surrounding response:

```python
return {"user": UserResource(user).to_dict(request)}
```

<a name="resource-collections"></a>
## Resource Collections

To transform a collection of models, use the resource's `collection` class method. A list of models serializes under a `data` key:

```python
@Route.get("/api/users", name="users.index")
async def index(request: Request):
    users = await User.all()
    return UserResource.collection(users).response(request)
```

This produces:

```json
{
  "data": [
    {"id": 1, "name": "Taylor", "email": "..."},
    {"id": 2, "name": "Abigail", "email": "..."}
  ]
}
```

<a name="paginated-collections"></a>
### Paginated Collections

Pass a [paginator](../orm/query-builder.md#pagination) instead of a list, and the collection emits the paginator's full envelope — your transformed items under `data`, plus pagination `meta` and `links`:

```python
@Route.get("/api/users", name="users.index")
async def index(request: Request):
    users = await User.paginate(per_page=20)
    return UserResource.collection(users).response(request)
```

```json
{
  "data": [ ... ],
  "meta": {
    "total": 150, "per_page": 20, "current_page": 1,
    "last_page": 8, "from": 1, "to": 20
  },
  "links": { ... }
}
```

When the request exposes its URL and query parameters, the `links` are rendered as full URLs (with the `page`/`cursor` query parameters managed for you); otherwise they fall back to page numbers.

<a name="conditional-attributes"></a>
## Conditional Attributes

Sometimes you may wish to only include an attribute in a resource response if a given condition is met. The `when` method includes a value only when its condition is truthy; otherwise the key is stripped from the output entirely:

```python
class UserResource(JsonResource[User]):
    def to_dict(self, request: Any) -> dict[str, Any]:
        return {
            "id": self.resource.id,
            "email": self.resource.email,
            "secret": self.when(self.resource.is_admin, "secret-value"),
        }
```

In this example, the `secret` key is only present in the final response if the user is an admin. For non-admins, the key is omitted — not set to `null`.

<a name="conditional-relationships"></a>
### Conditional Relationships

Including relationships conditionally is a common need, since you rarely want to trigger a database query just to serialize a response. The `when_loaded` method includes a relationship only if it has *already* been loaded onto the model:

```python
class UserResource(JsonResource[User]):
    def to_dict(self, request: Any) -> dict[str, Any]:
        return {
            "id": self.resource.id,
            "email": self.resource.email,
            "posts": self.when_loaded("posts"),
        }
```

> [!NOTE]
> `when_loaded` never lazy-loads. If the relation isn't already hydrated on the model, the key is stripped. Eager-load the relation first — for example with `with_("posts")` — to include it. This works for every relation type: SQLAlchemy relations hydrated on the model and Arvel's async relations (has-many, belongs-to-many, morph-to-many) cached by `with_()`. See [Relationships](../orm/relationships.md#eager-loading).

<a name="merging-conditional-data"></a>
### Merging Conditional Data

Sometimes you may need to include several attributes in the resource response, but only if a single condition is met. `merge_when` returns the given dictionary when the condition is truthy, or an empty dict otherwise — spread it into your output:

```python
class OrderResource(JsonResource[Order]):
    def to_dict(self, request: Any) -> dict[str, Any]:
        return {
            "id": self.resource.id,
            "total": self.resource.total,
            **self.merge_when(self.resource.is_paid, {
                "paid_at": self.resource.paid_at,
                "receipt_url": self.resource.receipt_url,
            }),
        }
```

<a name="adding-meta-data"></a>
## Adding Meta Data

You may add top-level data to a resource response with `additional`. Keys you supply are merged into the root of the response (and win over the resource's own keys on a clash):

```python
return UserResource(user).additional({"meta": {"version": 2}}).response(request)
```

`additional` is also available on collections:

```python
return UserResource.collection(users).additional({"meta": {"team": "core"}}).response(request)
```

<a name="customizing-the-response"></a>
## Customizing the Response

Both `JsonResource` and `ResourceCollection` expose `response(request, *, status_code=200, headers=None)`, which returns a `ResourceResponse` (a Starlette `JSONResponse` built from the resource envelope). Set the status and headers there:

```python
return UserResource(user).response(request, status_code=201)
```

<a name="documenting-the-response-schema"></a>
## Documenting the Response Schema

Set the `schema` class variable to a Pydantic model to declare the response shape for OpenAPI tooling:

```python
class UserOut(BaseModel):
    id: int
    email: str


class UserResource(JsonResource[User]):
    schema = UserOut

    def to_dict(self, request: Any) -> dict[str, Any]:
        return {"id": self.resource.id, "email": self.resource.email}
```

> [!NOTE]
> `schema` is a documentation convention — a hook for app-level OpenAPI tooling. The framework doesn't itself wire it into the generated schema, so keep the model in sync with what `to_dict` actually returns.
