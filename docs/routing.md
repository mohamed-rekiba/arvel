# Routing

Routing is the map of your application — which URL runs which code. arvel lets you draw that map
with short, expressive definitions (`Route.get("/users/{user}", show)`) and takes care of the rest:
it compiles them onto [Litestar](https://litestar.dev)'s router, so path parsing, parameter
coercion, and the OpenAPI schema all come from a real, battle-tested engine — you don't hand-roll
any of it. Every request then flows through the [middleware](middleware.md) pipeline before reaching
your handler.

This page covers the whole surface: defining routes, naming them and generating URLs (including
signed ones), resource controllers, binding path parameters straight to models, grouping, and
bailing out with an error.

!!! note "Needs the `[http]` extra"
    Routing is part of the core, but *serving* routes runs on Litestar — `uv add 'arvel[http]'`.

## Basic routes

```python
from arvel import Route

Route.get("/", home)
Route.post("/users", store)
Route.put("/users/{user}", update)
Route.delete("/users/{user}", destroy)
Route.match(["GET", "POST"], "/search", search)   # several verbs
Route.any("/legacy", legacy)                       # all verbs
```

A handler is any callable (sync or async); it receives the request and any path params, and
returns a dict/list/str (Litestar serializes it) or an explicit `Response`.

**Return a model or a collection directly** (Laravel parity) — the framework serializes an arvel
`Model`, a list of models, or a paginator of models to JSON via each model's `to_dict()` (hidden
fields and loaded relations honored):

```python
async def show(request):
    return await Product.with_("variants").find(request.path_param("id"))   # → a JSON object

async def index(request):
    return await Product.query().paginate()      # → Laravel's paginator JSON shape
```

### Redirect & view routes

For the common controller-less cases there are shortcuts:

```python
Route.redirect("/here", "/there")              # 302 → /there
Route.permanent_redirect("/old", "/new")       # 301
Route.view("/about", "pages.about", {"title": "About"})   # render a view, no controller
```

## Named routes & URL generation

Name a route, then reverse it to a URL — so links survive a path change:

```python
Route.get("/users/{user}", show, name="users.show")

router.url("users.show", user=7)                   # "/users/7"
```

Parameters that match a `{placeholder}` fill the path; any **extra** parameters are appended as
a query string:

```python
router.url("users.show", user=7, tab="profile")    # "/users/7?tab=profile"
```

`url()` fails loudly rather than rendering a wrong path: it raises `KeyError` for an unknown
route name, and `ValueError` if a required path parameter is missing (so a half-built link never
slips through with a literal `{user}` in it).

### Signed URLs

Tamper-evident links (password resets, unsubscribe, email confirmation) carry a signature over
the URL; an optional `expires` makes them temporary:

```python
link = router.signed_url("unsubscribe", user=7)            # key defaults to the app key
temp = router.signed_url("confirm", expires=ts, token=t)   # temporary (expires is a unix ts)

if router.has_valid_signature(request.full_url()):
    ...                                            # signature intact AND not expired
```

The signature is an itsdangerous MAC appended as a `signature` query param; verification checks
both integrity and (if present) that `expires` is still in the future. The signing key defaults to
the app key (`config('app.key')`); pass `key=` to override (a rotated key invalidates old links).

Protect a route declaratively with the **signed** middleware (Laravel's `signed`) instead of
checking by hand:

```python
from arvel.http.middleware import ValidateSignature

Route.get("/unsubscribe", unsubscribe, name="unsubscribe").middleware(ValidateSignature)
```

A request to that route without a valid (or with an expired) signature gets a **403** before the
handler runs.

## Resource controllers

One call registers a controller's RESTful routes:

```python
Route.resource("posts", PostController)            # 7 routes (with create/edit forms)
Route.api_resource("posts", PostController)         # 5 routes (no HTML form actions)
Route.resource("posts", PostController, only=["index", "show"])
Route.resource("posts", PostController, except_=["destroy"])
```

| Verb | URI | Action | Name |
|---|---|---|---|
| GET | `/posts` | index | `posts.index` |
| GET | `/posts/create` | create | `posts.create` |
| POST | `/posts` | store | `posts.store` |
| GET | `/posts/{post}` | show | `posts.show` |
| GET | `/posts/{post}/edit` | edit | `posts.edit` |
| PUT/PATCH | `/posts/{post}` | update | `posts.update` |
| DELETE | `/posts/{post}` | destroy | `posts.destroy` |

`only` / `except_` trim the set; `api_resource` drops the form-rendering `create`/`edit`.

### Authorizing every action at once

Call `authorize_resource(Model)` on the controller and each action is checked against the
model's [policy](auth/authorization.md) automatically — no per-method `authorize` calls:

```python
class PostController(Controller):
    async def index(self): ...
    async def show(self, post): ...

PostController.authorize_resource(Post)
```

The action → ability map is:

| Action | Ability | Authorized against |
|---|---|---|
| `index` | `viewAny` | the model class |
| `create` / `store` | `create` | the model class |
| `show` | `view` | the bound instance |
| `edit` / `update` | `update` | the bound instance |
| `destroy` | `delete` | the bound instance |

Instance actions authorize against the route-bound model (pair it with
[route–model binding](#routemodel-binding)); a denied check raises `403` before the action body
runs.

## Route–model binding

Bind a path param to a model so the handler receives the **resolved instance** (with an
automatic 404 when it's missing) instead of a raw string id.

### Implicit binding

Type-hint the action parameter with a model and arvel resolves it for you — no registration:

```python
from app.models import User

async def show(request, user: User):       # {user} -> the User with that id; 404 if none
    return UserResource(user)
```

The path param name (`{user}`) must match the argument name (`user`). By default the lookup is by
primary key; override the column a model binds on with `get_route_key_name`:

```python
class Post(Model):
    @classmethod
    def get_route_key_name(cls) -> str:
        return "slug"                      # /posts/{post} now resolves Post by slug
```

Or pick the column inline in the path with `{param:field}` — handy when a model is bound by
different columns on different routes:

```python
Route.get("/posts/{post:slug}", show)      # resolves Post by its slug column for this route
```

(`{x:path}`, `{x:int}`, and the other Litestar converters keep their meaning — only an unknown
suffix is treated as a route-key column.)

### Explicit binding

When you need a custom resolver, or want to bind without a type hint, register it on the router:

```python
router.model("user", User)                 # {user} -> resolve User by primary key; 404 on miss
router.model("post", Post, key="slug")     # bind by a custom column
router.bind("token", resolve_token)        # arbitrary resolver (sync or async); 404 on None
router.bind_enum("status", Status)         # coerce {status} to an enum member (404 if invalid)
```

Explicit bindings take precedence over implicit ones for the same parameter.

## Aborting a request

When a handler needs to bail out with an HTTP error, call `abort()` — it raises an
`HttpException` the framework renders content-negotiated (JSON for API clients, an error page for
the browser), exactly like a failed validation:

```python
from arvel import abort

async def show(request, post):
    if post.archived:
        abort(404)                       # → 404 "Not Found"
    if not request.user.owns(post):
        abort(403, "That isn't yours.")  # → 403 with your own message
    return post
```

With no message, `abort(status)` uses the standard status text (`404` → "Not Found"); pass a
second argument to override it. Route–model binding already aborts with `404` on a miss, so you
rarely abort manually for the not-found case.

## Groups

When a set of routes share a prefix, a name prefix, or the same middleware, declare it once with a
`group` block instead of repeating yourself on every line:

```python
with router.group(prefix="/admin", name="admin.") as admin:
    admin.get("/dashboard", dashboard, name="dashboard")   # /admin/dashboard, "admin.dashboard"
    admin.get("/users", users, name="users")               # /admin/users,    "admin.users"
```

A group can also attach **middleware** to everything inside it, and assign a named middleware
[group](middleware.md) (`"web"`/`"api"`) in one place:

```python
with router.group(prefix="/admin", middleware=[EnsureAdmin], group="web") as admin:
    admin.get("/dashboard", dashboard)     # runs EnsureAdmin + the web group (session + CSRF)
```

Groups **nest**, and the prefixes, names, and middleware compose — an inner group runs both its own
and the outer group's middleware, and everything is restored when the block exits:

```python
with router.group(prefix="/api", group="api") as api:
    with api.group(prefix="/v1", name="v1.") as v1:
        v1.get("/stats", stats, name="stats")   # /api/v1/stats, "v1.stats", throttled by "api"
```

## Middleware & fallback

Assign a route to a middleware [group](middleware.md), and register a catch-all:

```python
Route.get("/dashboard", show, group="web")     # session + CSRF
Route.get("/api/stats", stats, group="api")    # throttled
Route.fallback(not_found)                        # matched when nothing else does
```

## Common mistakes & gotchas

- **Reversing an unknown name.** `url("typo")` raises `KeyError` — keep names in sync with
  definitions; a test that reverses every named route catches drift.
- **Unbound path param.** `{user}` stays a raw string unless the handler argument is type-hinted
  with a model (implicit binding) or you register `router.model(...)`/`bind(...)`. For implicit
  binding the argument **name must match** the placeholder (`{user}` → `user: User`).
- **Signed link with a different key.** `has_valid_signature` must use the *same* key the URL was
  signed with; a rotated key invalidates old links (intended).

## How it works

`Route`/`Router` collect `RouteDefinition`s; `apply_to(kernel)` adapts each onto a Litestar
`HTTPRouteHandler` (arvel `{id}` → Litestar `{id:str}`), so the served app *is* a Litestar app
and its OpenAPI schema is Litestar-generated from the registered routes — not hand-written.
Bindings resolve in the kernel before the handler runs.

## See also

- [Middleware](middleware.md) — the web/api groups routes attach to.
- [Validation](validation.md) — validating request input in handlers.
- [Views](views.md) — `Route.view(...)`, rendering, and template globals.
- [OpenAPI & API docs](openapi.md) — the auto-generated schema, request/response models, and auth.
