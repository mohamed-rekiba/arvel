# Routing

<a name="introduction"></a>
## Introduction

A route maps an incoming HTTP request to the code that handles it. In Arvel, that code is a plain `async def` function — a route handler — decorated with one of the `Route` verb decorators:

```python
from arvel import Route


@Route.get("/api/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
```

Under the hood, Arvel mounts every route onto the underlying [FastAPI](https://fastapi.tiangolo.com) application when the app boots. That has a practical upside: path parameters, query parameters, request bodies, and dependency injection all behave exactly as they do in FastAPI, because your handler *is* a FastAPI route. Arvel layers a Laravel-style routing API — named routes, route groups, model binding, resource routes, signed URLs — on top of that foundation.

> [!NOTE]
> Because handlers are FastAPI routes, anything FastAPI understands in a function signature works here: Pydantic models for request bodies, `Query(...)`/`Path(...)` markers, `UploadFile`, and so on. The Arvel-specific pieces are the decorators, groups, model binding, and the `route()` / `URL` helpers documented on this page.

<a name="basic-routing"></a>
## Basic Routing

The most basic route accepts a path and returns a value. Returning a `dict`, a `list`, a Pydantic model, or a primitive lets FastAPI serialize the response to JSON with a `200` status:

```python
from arvel import Route


@Route.get("/api/greeting")
async def greeting() -> dict[str, str]:
    return {"message": "Hello World"}
```

<a name="the-default-route-files"></a>
### The Default Route Files

Routes are defined in files registered with the application builder. A freshly scaffolded project wires three paths in `bootstrap/app.py`:

```python
.with_routing(
    web=routes_dir / "web.py",
    api=routes_dir / "api.py",
    console=routes_dir / "console.py",
)
```

When the application is created, Arvel imports `routes/web.py` and `routes/api.py`, executing the decorators inside them so the routes register themselves. Put your HTTP routes in either file — the split is organizational, not functional.

> [!WARNING]
> There is **no** automatic `/api` prefix applied to routes in `routes/api.py`. Whatever path you write is the path that's served. The skeleton uses full paths like `/api/healthz`. If you want every API route under `/api`, wrap them in a [route group](#prefixes) with `prefix="/api"`.

> [!NOTE]
> The `console` path is reserved for console route definitions and is **not loaded yet**. Define console commands as classes today — see the [CLI reference](../cli/commands.md).

<a name="available-router-methods"></a>
### Available Router Methods

The router lets you register handlers for any standard HTTP verb:

```python
@Route.get("/resource")
@Route.post("/resource")
@Route.put("/resource")
@Route.patch("/resource")
@Route.delete("/resource")
@Route.head("/resource")
@Route.options("/resource")
```

Every verb decorator shares the same keyword arguments:

| Keyword | Type | Purpose |
|---|---|---|
| `path` | `str` | The URL path (positional). Prefixed by any enclosing group. |
| `name` | `str \| None` | A [name](#named-routes) for URL generation. |
| `middleware` | `Sequence[Middleware \| str] \| None` | [Middleware](middleware.md) instances or named-group strings. |
| `controller` / `action` | `type` / `str` | Bind the route to a [controller](controllers.md) method. |
| `**extras` | `Any` | Forwarded to FastAPI's route registration (e.g. `status_code`, `tags`, `response_model`, `include_in_schema`). |

The `**extras` passthrough is how you set a non-200 status or tune the OpenAPI schema:

```python
@Route.post("/api/users", name="users.store", status_code=201, tags=["users"])
async def store(payload: CreateUserPayload) -> dict[str, str]:
    ...
```

> [!NOTE]
> Arvel does not provide `Route.any` or `Route.match`. Register the specific verbs you need. To respond to several verbs on one path, stack decorators (each registers a distinct route).

<a name="view-and-redirect-routes"></a>
### View and Redirect Routes

Arvel has no `Route.view` or `Route.redirect` shortcut. Return a Starlette response from a normal handler instead:

```python
from starlette.responses import RedirectResponse


@Route.get("/old-path")
async def old_path() -> RedirectResponse:
    return RedirectResponse("/new-path", status_code=302)
```

<a name="route-parameters"></a>
## Route Parameters

<a name="required-parameters"></a>
### Required Parameters

Capture segments of the URL by wrapping a name in braces. The captured value is passed to your handler as an argument with the matching name:

```python
@Route.get("/api/users/{user_id}")
async def show(user_id: int) -> dict[str, int]:
    return {"user_id": user_id}
```

Define as many parameters as the route requires:

```python
@Route.get("/api/posts/{post_id}/comments/{comment_id}")
async def show(post_id: int, comment_id: int) -> dict[str, int]:
    return {"post_id": post_id, "comment_id": comment_id}
```

<a name="optional-and-typed-parameters"></a>
### Optional and Typed Parameters

Parameter typing and optionality come from FastAPI. Annotate the handler argument with the type you want, and Arvel/FastAPI coerces and validates the incoming value — a non-integer sent to an `int` parameter produces a `422` automatically:

```python
@Route.get("/api/users/{user_id}")
async def show(user_id: int) -> dict[str, int]:
    # "/api/users/abc" → 422 before this body runs
    return {"user_id": user_id}
```

Query parameters and defaults work the same way — anything that isn't a path placeholder is read from the query string:

```python
@Route.get("/api/posts/{post_id}")
async def show(post_id: int, page: int = 1) -> dict[str, int]:
    # GET /api/posts/1?page=7 → page == 7
    return {"post_id": post_id, "page": page}
```

<a name="regular-expression-constraints"></a>
### Regular Expression Constraints

Arvel does not add a routing-layer constraint DSL — there is no `where()` method and no global pattern registry. Constrain parameters with the tools FastAPI already gives you: type annotations (shown above) or FastAPI path converters written directly in the path string.

> [!NOTE]
> Path placeholders in Arvel use the form `{name}`. Type coercion, validation, and any converter syntax are handled by FastAPI, not by an Arvel-specific layer.

<a name="named-routes"></a>
## Named Routes

Named routes let you generate URLs without hard-coding paths. Assign a name with the `name` keyword:

```python
@Route.get("/api/users/{user_id}", name="users.show")
async def show(user_id: int) -> dict[str, int]:
    return {"user_id": user_id}
```

Generate a URL to the route by name (see [URL Generation](#url-generation)):

```python
from arvel.routing import route

route("users.show", user_id=42)   # "/api/users/42"
```

Looking up a name that was never registered raises `RouteNotFoundError`.

> [!WARNING]
> Route names are not checked for uniqueness. If two routes share a name, URL generation resolves to the first one registered. Keep names unique.

<a name="route-groups"></a>
## Route Groups

Route groups let many routes share attributes — a path prefix, middleware, a name prefix — without repeating them on every route. `Route.group` is a context manager; every route declared inside the `with` block inherits the group's attributes:

```python
from arvel.http.middleware import Authenticate, Throttle


with Route.group(prefix="/api", middleware=[Authenticate()], name_prefix="api."):
    @Route.get("/profile", name="profile")
    async def profile() -> dict[str, str]:
        return {"ok": "yes"}
    # path: /api/profile, name: api.profile, runs behind Authenticate
```

The middleware examples below reuse these `Authenticate` / `Throttle` imports.

<a name="prefixes"></a>
### Prefixes

`prefix` prepends a path segment to every route in the group:

```python
with Route.group(prefix="/api/v1"):
    @Route.get("/users")     # → /api/v1/users
    async def users() -> list[dict]:
        ...
```

<a name="group-middleware"></a>
### Middleware

`middleware` attaches one or more [middleware](middleware.md) to every route in the group. Pass instances or names registered as middleware groups:

```python
with Route.group(middleware=[Authenticate(), Throttle(60)]):
    @Route.get("/api/dashboard")
    async def dashboard() -> dict[str, str]:
        ...
```

<a name="name-prefixes"></a>
### Name Prefixes

`name_prefix` is prepended to the `name` of every named route in the group. Include the trailing dot you want in the final name:

```python
with Route.group(name_prefix="admin."):
    @Route.get("/admin/users", name="users.index")   # name → admin.users.index
    async def index() -> list[dict]:
        ...
```

<a name="nesting-groups"></a>
### Nesting Groups

Groups nest. Prefixes, middleware, and name prefixes concatenate from the outer group inward:

```python
with Route.group(prefix="/api", middleware=[Throttle(60)]):
    with Route.group(prefix="/v1", name_prefix="v1."):
        @Route.get("/users", name="users.index")
        async def users() -> list[dict]:
            ...
        # path: /api/v1/users
        # name: v1.users.index
        # middleware: [Throttle(60)]
```

[Explicit bindings](#explicit-binding) declared inside a group apply only to routes in that group, and an inner binding overrides an outer one for the same parameter name.

<a name="route-model-binding"></a>
## Route Model Binding

When a route parameter names a model, it's tedious to take the id, query for the record, and 404 if it's missing on every route. Route model binding does that for you: annotate a handler parameter with an ORM `Model` subclass and Arvel resolves the instance from the database before your handler runs.

<a name="implicit-binding"></a>
### Implicit Binding

Type-hint the parameter with the model. The path value is looked up by primary key:

```python
from app.models.post import Post


@Route.get("/api/posts/{post}")
async def show(post: Post) -> dict:
    # path value resolved via Post.find(value); a missing row → 404
    return post.to_dict()
```

If no matching record is found, Arvel raises `NotFoundException`, which the [error handler](error-handling.md) turns into a `404` response.

> [!NOTE]
> Binding resolves through the model's query builder, so global scopes — soft deletes, for example — are applied. A soft-deleted record won't be found by an implicit binding.

<a name="customizing-the-key"></a>
### Customizing the Key

To resolve by a column other than the primary key, set `route_key_name` on the model. Arvel then looks the record up with `Model.where(route_key_name=value).first()`:

```python
from typing import ClassVar

from arvel.database import Model


class Post(Model):
    route_key_name: ClassVar[str] = "slug"
    # "/api/posts/hello-world" → Post.where(slug="hello-world").first()
```

<a name="explicit-binding"></a>
### Explicit Binding

For full control over resolution, register an explicit binding with `Route.bind`. The resolver receives the raw path string and returns the resolved value (or `None` for a `404`):

```python
from arvel import Route
from app.models.post import Post


async def resolve_post(value: str) -> Post | None:
    return await Post.where(slug=value).first()


Route.bind("post", resolve_post)


@Route.get("/api/posts/{post}")
async def show(post: Post) -> dict:
    return post.to_dict()
```

Explicit bindings take precedence over implicit binding for the same parameter name. Call `Route.bind` at module scope for an app-wide binding, or inside a `with Route.group():` block to scope it to that group.

<a name="resource-routes"></a>
## Resource Routes

A resource controller handles all the "CRUD" routes for a resource in one class. `Route.resource` registers the conventional routes for that controller in a single call:

```python
from app.http.controllers.post_controller import PostController

Route.resource("/api/posts", PostController)
```

That one line registers seven routes:

| Verb | Path | Action (method) | Route Name |
|---|---|---|---|
| GET | `/api/posts` | `index` | `posts.index` |
| GET | `/api/posts/create` | `create` | `posts.create` |
| POST | `/api/posts` | `store` | `posts.store` |
| GET | `/api/posts/{post}` | `show` | `posts.show` |
| GET | `/api/posts/{post}/edit` | `edit` | `posts.edit` |
| PUT | `/api/posts/{post}` | `update` | `posts.update` |
| DELETE | `/api/posts/{post}` | `destroy` | `posts.destroy` |

Your controller implements the matching methods. See [Controllers](controllers.md#resource-controllers) for the controller side.

For JSON APIs, the `create` and `edit` actions — which exist to render HTML forms — are unnecessary. `Route.api_resource` registers the same routes **without** them:

```python
Route.api_resource("/api/posts", PostController)
# index, store, show, update, destroy (no create / edit)
```

> [!NOTE]
> The `update` route is registered as `PUT`, not `PATCH`. Nested resource routes (e.g. `/posts/{post}/comments`) are not generated automatically — register those explicitly.

<a name="partial-resource-routes"></a>
### Partial Resource Routes

`Route.resource` and `Route.api_resource` return a registration object you can refine fluently. Use `only` and `except_` to limit which actions are registered:

```python
Route.api_resource("/api/posts", PostController).only("index", "show")

Route.resource("/api/posts", PostController).except_("destroy")
```

Passing an action name that isn't one of the seven raises `ValueError`.

<a name="naming-resource-routes"></a>
### Naming Resource Routes

Override the default route names with `names`:

```python
Route.resource("/api/posts", PostController).names({
    "index": "posts.list",
    "show": "posts.view",
})
```

<a name="customizing-the-parameter"></a>
### Customizing the Parameter

By default the member parameter is the singularized last path segment — `/api/posts` yields `{post}`. Override it with `parameter`:

```python
Route.api_resource("/api/posts", PostController, parameter="article")
# member routes use /{article} instead of /{post}
```

Attach middleware to every action in the resource with the `middleware` keyword:

```python
Route.api_resource("/api/posts", PostController, middleware=[Authenticate()])
```

<a name="url-generation"></a>
## URL Generation

Arvel ships helpers for generating URLs to your routes. Import them from `arvel.routing`:

```python
from arvel.routing import route, url, URL
```

The `url()` helper turns a path into an absolute URL using the application's configured `APP_URL`. URLs that are already absolute are returned unchanged:

```python
url("/avatar.png")          # "https://example.com/avatar.png"
url("https://cdn.test/x")   # "https://cdn.test/x"  (unchanged)
```

> [!WARNING]
> `url()`, and `route(..., absolute=True)`, require `APP_URL` to be set. Without it, they raise `RoutingError`.

<a name="generating-urls-to-named-routes"></a>
### Generating URLs to Named Routes

`route()` builds a URL for a [named route](#named-routes). Pass each route parameter as a keyword argument:

```python
route("users.show", user_id=42)                  # "/api/users/42"  (relative path)
route("users.show", user_id=42, absolute=True)   # "https://example.com/api/users/42"
```

If the name doesn't exist, `route()` raises `RouteNotFoundError`. If a required `{parameter}` isn't supplied, it raises `RoutingError`.

<a name="signed-urls"></a>
### Signed URLs

A signed URL has a tamper-proof signature appended to its query string, letting you verify it wasn't modified after you generated it. Signed URLs are ideal for publicly accessible links like "unsubscribe" or "verify email" actions. Generate one with `URL.signed_route`. Keyword arguments fill the route's `{placeholders}` — they aren't added to the query string — so put any data you want to sign in the path:

```python
from arvel.routing import URL

# route registered as "/unsubscribe/{token}" with name "unsubscribe"
signed = URL.signed_route("unsubscribe", token="abc")
# "https://example.com/unsubscribe/abc?signature=<hmac-sha256>"
```

To make the link expire, pass `expires_at`:

```python
import time
from datetime import UTC, datetime, timedelta

# A timezone-aware datetime...
URL.signed_route("unsubscribe", token="abc", expires_at=datetime.now(UTC) + timedelta(hours=1))

# ...or a Unix timestamp (seconds).
URL.signed_route("unsubscribe", token="abc", expires_at=int(time.time()) + 3600)
```

> [!WARNING]
> `expires_at` is an **absolute** expiry — a timezone-aware `datetime` or a Unix timestamp — not a "seconds from now" duration. A naive `datetime` (without a timezone) raises `ValueError`. Signing requires `APP_KEY` to be set; see [Encryption](../features/encryption.md).

Validate an incoming signed request with `URL.has_valid_signature`, which checks the signature and the expiry:

```python
from arvel import NotFoundException, Route
from arvel.routing import URL
from starlette.requests import Request


@Route.get("/unsubscribe/{token}", name="unsubscribe")
async def unsubscribe(request: Request, token: str):
    if not URL.has_valid_signature(request):
        raise NotFoundException("Invalid or expired link.")
    ...
```

To protect a whole group of routes, attach `SignedMiddleware`, which returns a `403` when the signature is invalid:

```python
from arvel.http.middleware import SignedMiddleware

with Route.group(middleware=[SignedMiddleware()]):
    @Route.get("/unsubscribe", name="unsubscribe")
    async def unsubscribe(token: str):
        ...
```

<a name="registering-routes-from-a-provider"></a>
## Registering Routes From a Provider

Decorators in `routes/api.py` and `routes/web.py` cover most apps. For routes you'd rather register programmatically — say, generated from config — implement a `RouteServiceProvider`. Its `map_routes` method runs on boot against the application's single `Router`:

```python
from arvel.routing import RouteServiceProvider, Router


class AppRouteServiceProvider(RouteServiceProvider):
    def map_routes(self, router: Router) -> None:
        # register routes programmatically here
        ...
```

Register named middleware groups on the router so routes can reference them by string:

```python
from arvel.http.middleware import Authenticate, Throttle


class AppRouteServiceProvider(RouteServiceProvider):
    def map_routes(self, router: Router) -> None:
        router.middleware_group("api", [Throttle(60), Authenticate()])
```

Routes can then opt in with `middleware=["api"]`.

<a name="inspecting-your-routes"></a>
## Inspecting Your Routes

The `route:list` command prints every registered route — method, URI, name, action, and middleware:

```bash
arvel route:list
```

Filter by a path substring, or emit JSON for tooling:

```bash
arvel route:list --filter posts
arvel route:list --json
```

> [!NOTE]
> Route caching is not yet available — `optimize`'s `route:cache` step is a no-op pending a route serializer.
