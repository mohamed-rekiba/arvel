# Routing

If you have used Laravel’s router, Arvel will feel familiar. The HTTP layer wraps FastAPI’s `APIRouter` with route groups, named routes, resource-style CRUD registration, and a small discovery convention so your `routes/` folder stays organized. Under the hood it is still Starlette and OpenAPI-aware—Arvel just gives you nicer ergonomics for the kinds of apps people build every day.

## The `Router` class

Create a module-level `router` instance and register paths with `get`, `post`, `put`, `patch`, or `delete`. Each method accepts either an endpoint directly or works as a decorator, mirroring FastAPI’s flexibility.

```python
from arvel.http import Router

router = Router()


@router.get("/health", name="health.check")
async def health() -> dict[str, str]:
    return {"status": "ok"}


router.post("/posts", endpoint=create_post, name="posts.store")
```

Route names must be unique on that router. Duplicate names raise `RouteRegistrationError` with both paths so you can fix collisions quickly.

## Path parameters

Arvel passes through FastAPI’s path syntax. Use `{name}` segments and declare matching parameters on your endpoint (or rely on dependency injection). Named routes and `url_for` use the same brace placeholders when you generate URLs.

```python
@router.get("/users/{user_id}", name="users.show")
async def show_user(user_id: int) -> dict[str, int]:
    return {"user_id": user_id}
```

## Route groups

Wrap related registrations in `router.group(...)` to share a URL prefix, middleware aliases, and a name prefix. Groups nest: each level adds to the cumulative prefix, middleware list, and name prefix.

```python
with router.group(prefix="/api/v1", middleware=["auth"], name="api."):
    router.get("/profile", name="profile", endpoint=profile)  # name: api.profile, path: /api/v1/profile
```

This keeps API versioning and auth middleware declarations in one place instead of repeating strings on every line.

## Named routes and URL generation

Every route can take `name=`. Later, call `router.url_for("users.show", user_id=42)` to get the path string with parameters substituted. Missing parameters raise a clear `RouteRegistrationError`.

For absolute URLs or signed links, use `UrlGenerator`, which wraps a `Router` and optional `base_url` (and signing helpers for tamper-proof links).

```python
from arvel.http import UrlGenerator

urls = UrlGenerator(router, base_url="https://app.example.com")
full = urls.url_for("users.show", user_id=1)  # https://app.example.com/users/1
```

## Resource routes

`router.resource(name, controller, ...)` registers the conventional REST actions: `index`, `store`, `show`, `update`, and `destroy`. Route names follow `{resource}.{action}` (for example `posts.index`, `posts.show`). Your controller class must define the corresponding methods.

You can limit actions with `only=["index", "show"]` or exclude some with `except_=["destroy"]`. Per-resource middleware aliases are supported the same way as on single routes.

```python
router.resource("posts", PostController, middleware=["throttle"])
```

## Per-route middleware

Pass `middleware=["alias1", "alias2"]` on a route (or inside a group). Aliases resolve through `HttpSettings.middleware_aliases` at boot. Use `without_middleware=["alias"]` to strip specific middleware from a route inside a grouped stack—handy for a public login endpoint under an otherwise authenticated API group.

## Discovering route modules

`discover_routes(base_path)` scans `routes/*.py` under your application root (skipping files that start with `_`). Each file should export a module-level `router` that is an instance of `Router`. The HTTP service provider includes those routers on the FastAPI app in sorted order and wires per-route middleware.

Typical layout:

```text
routes/
  web.py      # router = Router() ...
  api.py      # router = Router() ...
```

That convention keeps route files small and lets you split concerns without a central import list that never stops growing.

## Tips

- Prefer meaningful `name=` values early; they power `url_for`, tests, and signed URLs.
- Keep group prefixes without a trailing slash; Arvel normalizes joining with inner paths.
- If OpenAPI matters, pass through FastAPI kwargs accepted by `add_api_route` on individual registrations or controller metadata merges.
