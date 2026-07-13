# Routing

Routing is the map of your application — which URL runs which code. arvel lets you draw that map
with short, expressive definitions (`Route.get("/users/{user}", show)`) and takes care of the rest:
it compiles them onto [Litestar](https://litestar.dev)'s router, so path parsing, parameter
coercion, and the OpenAPI schema all come from a real, battle-tested engine. Every request then
flows through the [middleware](middleware.md) pipeline before reaching your handler.

!!! note "Needs the `[http]` extra"
    Routing is part of the core, but *serving* routes runs on Litestar — `uv add 'arvel[http]'`.

## Basic routing

The most basic routes accept a URI and a handler (any sync or async callable):

```python
from arvel import Route

Route.get("/", home)
Route.post("/users", store)
Route.put("/users/{user}", update)
Route.patch("/users/{user}", partial_update)
Route.delete("/users/{user}", destroy)
Route.match(["GET", "POST"], "/search", search)   # several verbs
Route.any("/legacy", legacy)                       # all verbs
```

A handler receives the request and any path params, and returns a dict/list/str (Litestar
serializes it) or an explicit `Response`. **Return a model or collection directly** and the
framework serializes it to JSON via each model's `to_dict()`:

```python
async def show(request):
    return await Product.with_("variants").find(request.path_param("id"))   # → a JSON object

async def index(request):
    return await Product.paginate()   # → the paginator JSON shape
```

Pin the response status with `.status(code)` — handy for a 200 action that returns a body but
isn't creating a resource (POST otherwise defaults to 201):

```python
Route.post("/login", login).status(200)
```

### Redirect & view routes

For the common controller-less cases there are shortcuts:

```python
Route.redirect("/here", "/there")              # 302 → /there
Route.permanent_redirect("/old", "/new")       # 301
Route.view("/about", "pages.about", {"title": "About"})   # render a view, no controller
```

## Route parameters

### Required parameters

Capture a segment of the URI with a `{param}` placeholder; it is passed to the handler by name:

```python
Route.get("/users/{user}/posts/{post}", show)

async def show(request, user, post):   # names match the placeholders
    ...
```

### Optional & catch-all parameters

Use a `:path` converter to capture the rest of the URI (including slashes) — the arvel idiom for an
optional/catch-all tail:

```python
Route.get("/files/{path:path}", serve)    # matches /files/a/b/c.txt → path="a/b/c.txt"
```

### Regular expression constraints

Constrain a parameter to a regex with `.where(param, pattern)`; a request whose segment doesn't
match simply doesn't match the route:

```python
Route.get("/users/{user}", show).where("user", r"[0-9]+")     # numeric ids only
Route.get("/posts/{slug}", show).where("slug", r"[a-z\-]+")
```

The `{param:int}`, `{param:uuid}`, and other Litestar converters are also available inline for the
common cases.

## Named routes

Name a route, then reverse it to a URL — so links survive a path change:

```python
Route.get("/users/{user}", show, name="users.show")

route("users.show", user=7)     # "/users/7"
```

Generating URLs to named routes (query strings, signed and temporary links, the `url()` accessors)
is covered in [URL Generation](urls.md).

## Route groups

When a set of routes share a prefix, a name prefix, or the same middleware, declare it once with a
`group` block instead of repeating yourself:

```python
with router.group(prefix="/admin", name="admin.") as admin:
    admin.get("/dashboard", dashboard, name="dashboard")   # /admin/dashboard, "admin.dashboard"
    admin.get("/users", users, name="users")               # /admin/users,    "admin.users"
```

### Middleware

A group can attach **middleware** to everything inside it, and assign a named middleware
[group](middleware.md) (`"web"`/`"api"`) in one place:

```python
with router.group(prefix="/admin", middleware=[EnsureAdmin], group="web") as admin:
    admin.get("/dashboard", dashboard)     # runs EnsureAdmin + the web group (session + CSRF)
```

Groups **nest** — prefixes, names, and middleware compose, and an inner group runs both its own and
the outer group's middleware:

```python
with router.group(prefix="/api", group="api") as api:
    with api.group(prefix="/v1", name="v1.") as v1:
        v1.get("/stats", stats, name="stats")   # /api/v1/stats, "v1.stats", throttled by "api"
```

### Subdomain routing

`group(domain=...)` constrains every route in the block to a `Host` header pattern — handy for a
tenant subdomain or splitting an admin host from the public one:

```python
with router.group(domain="{account}.example.com"):
    router.get("/dashboard", dashboard)   # only matches e.g. acme.example.com

async def dashboard(request, account: str):   # {account} injected like a path param
    ...
```

A request whose `Host` doesn't match renders a plain 404 — never a mis-bind onto the wrong tenant.
Declare the most specific domain first if you also register a domain-less catch-all at that path.

## Route model binding

Bind a path param to a model so the handler receives the **resolved instance** (with an automatic
404 when it's missing) instead of a raw string id.

### Implicit binding

Type-hint the action parameter with a model and arvel resolves it — no registration:

```python
from app.models import User

async def show(request, user: User):       # {user} -> the User with that id; 404 if none
    return UserResource(user)
```

The path param name (`{user}`) must match the argument name (`user`).

### Customizing the key

By default the lookup is by primary key. Override the column a model binds on with
`get_route_key_name`, or pick it inline per route with `{param:field}`:

```python
class Post(Model):
    @classmethod
    def get_route_key_name(cls) -> str:
        return "slug"                      # /posts/{post} now resolves Post by slug

Route.get("/posts/{post:slug}", show)      # …or just this route, by slug
```

### Soft-deleted models

Binding excludes soft-deleted rows by default. Let a specific route include them with
`.with_trashed()`:

```python
Route.get("/posts/{post}", show).with_trashed()
Route.get("/posts/{post}/comments/{comment}", show).with_trashed("comment")   # just {comment}
```

### Scoping nested bindings

`/users/{user}/posts/{post}` resolves `{post}` on its own by default. Opt into **parent-scoped**
resolution with `.scope_bindings()`, so `{post}` resolves through `User`'s `posts()` relation and a
post that isn't the user's 404s:

```python
Route.get("/users/{user}/posts/{post}", show).scope_bindings()
```

### Missing model behavior

By default a missing bound model aborts with 404. Override that per route with `.missing(callback)`
to redirect or render something else instead:

```python
Route.get("/posts/{post}", show).missing(lambda request: redirect("/posts"))
```

### Explicit binding

When you need a custom resolver or want to bind without a type hint, register it on the router:

```python
router.model("user", User)                 # {user} -> resolve User by primary key
router.model("post", Post, key="slug")     # bind by a custom column
router.bind("token", resolve_token)        # arbitrary resolver (sync or async); 404 on None
router.bind_enum("status", Status)         # coerce {status} to an enum member (404 if invalid)
```

Explicit bindings take precedence over implicit ones for the same parameter.

## Fallback routes

Register a catch-all for requests that match no other route:

```python
Route.fallback(not_found)      # matched only when nothing else does
```

To serve a `public/` directory as an SPA shell (any non-file path falls back to `index.html`), use
`Route.public(...)` — or configure it once at boot so no route-file code is needed:

```python
Route.public("public")                                    # serve ./public at the root
Route.public("public", spa_fallback=False)                # static files only, no SPA shell
Application.configure(base_path=".").with_public_dir("public").create()
```

A more specific route always wins on its own path regardless of registration order.

## Form method spoofing

HTML forms can only send `GET` and `POST`. To route a form submission as `PUT`, `PATCH`, or `DELETE`,
add a `_method` field — the `MethodOverride` middleware rewrites the method before the router matches:

```html
<form action="/posts/{{ post.id }}" method="POST">
  {{ method_field("PUT") }}   <!-- <input type="hidden" name="_method" value="PUT"> -->
  {{ csrf_field() }}
</form>
```

```python
Route.put("/posts/{post}", update)   # the spoofed POST reaches this route
```

Only `PUT`/`PATCH`/`DELETE` are spoofable, and only on a `POST` with a form content type
(urlencoded or multipart).

## Accessing the current route

Inside a handler (or anything it calls), read the matched route back — its name and resolved params
(a model-bound param carries the resolved model, not the raw id):

```python
from arvel import url

async def show(request, post):
    match = url().current_route()                     # RouteMatch(name=..., params={...}) | None
    is_admin = url().current_route_named("admin.*")   # fnmatch glob on the name
```

`Route.current_route()`/`Route.current_route_named(...)` read the same thing; both degrade to
`None`/`False` outside a request rather than raising.

## See also

- [Controllers](controllers.md) — grouping route logic into classes, resource controllers.
- [URL Generation](urls.md) — reversing named routes, signed and temporary URLs.
- [Middleware](middleware.md) — the web/api groups routes attach to.
- [Error Handling](errors.md) — `abort()` and rendering HTTP errors from a handler.
