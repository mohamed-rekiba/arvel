# Routing

The most basic Arvel routes accept a URI and a handler function. You can define a route with one decorator, and the framework takes care of the rest — parameter coercion, validation, OpenAPI generation, and middleware.

`Route` is the facade you use to register routes. Under the hood, `Router` wraps `fastapi.APIRouter` and applies Arvel's two-tier middleware pipeline.

## Registering routes

Every HTTP verb is a class method on `Route`:

```python
from arvel import Route


@Route.get("/users/{user_id}", name="users.show")
async def show(user_id: str) -> dict[str, str]:
    return {"id": user_id}
```

The decorator buffers a `RouteSpec` inside the singleton `Router`. When you call `Application.into_asgi()`, those specs are mounted on the ASGI app.

### Available router methods

```python
Route.get(uri, ...)
Route.post(uri, ...)
Route.put(uri, ...)
Route.patch(uri, ...)
Route.delete(uri, ...)
Route.head(uri, ...)
Route.options(uri, ...)
```

## Route parameters

Path parameters are declared with FastAPI's `{name}` syntax. Type-annotate them and FastAPI handles the coercion:

```python
@Route.get("/posts/{post_id}/comments/{comment_id}")
async def show_comment(post_id: int, comment_id: int) -> dict[str, int]:
    return {"post": post_id, "comment": comment_id}
```

### Constraining parameters

For more advanced constraints, use Pydantic's `Annotated`:

```python
from typing import Annotated
from pydantic import Field


@Route.get("/users/{user_id}")
async def show(
    user_id: Annotated[int, Field(ge=1, le=999_999_999)],
) -> dict[str, int]:
    return {"id": user_id}
```

Out-of-range values produce a `422` automatically.

### Optional parameters

Path parameters are required by definition. For optional values, use query strings:

```python
@Route.get("/search")
async def search(q: str = "") -> dict[str, str]:
    return {"query": q}
```

## Route model binding

Type a path parameter with a `Model` subclass and Arvel will resolve the row from the database before the handler runs. Hit `/posts/5` and `post` arrives as a loaded `Post` instance — no manual `find_or_fail` calls.

```python
from arvel import Route
from arvel.database import Model
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class Post(Model):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    title: Mapped[str] = mapped_column(String(80), nullable=False)


@Route.get("/posts/{post}")
async def show(post: Post) -> dict[str, str]:
    return {"id": post.id, "title": post.title}
```

A miss returns `404 NOT_FOUND` through the standard `HttpExceptionHandler` JSON envelope — the handler never runs.

### Custom route keys

By default the URL value is matched against the model's primary key. Override `route_key_name` to bind against another column — slugs are the common case:

```python
from typing import ClassVar


class Article(Model):
    __tablename__ = "articles"

    route_key_name: ClassVar[str] = "slug"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, init=False, default=None)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)


@Route.get("/articles/{article}")
async def show(article: Article) -> dict[str, str]:
    return {"slug": article.slug}
```

`/articles/hello-world` now resolves via `Article.where(slug="hello-world").first()`.

### Custom resolvers with `Route.bind`

When the default lookup isn't enough — soft-deleted rows, multi-key lookups, totally synthetic parameters — register a resolver with `Route.bind(name, resolver)`:

```python
from arvel.routing import Route


async def _with_trashed(raw: str) -> Post | None:
    return await Post.with_trashed().where(id=raw).first()


Route.bind("post", _with_trashed)


@Route.get("/admin/posts/{post}")
async def show(post: Post) -> dict[str, str]:
    return {"id": post.id}
```

The resolver receives the raw URL string and runs at request time. Returning `None` raises `NotFoundException`, same as the implicit path. Explicit resolvers always win over implicit binding when both could apply to the same parameter name.

Resolvers can also produce non-Model values — the handler annotation is irrelevant to the binder:

```python
async def _decode_token(raw: str) -> dict[str, str]:
    return {"raw": raw, "decoded": raw.upper()}


Route.bind("token", _decode_token)


@Route.get("/tokens/{token}")
async def show(token: dict[str, str]) -> dict[str, str]:
    return token
```

### Group-scoped bindings

Bindings declared outside any `Route.group()` block apply globally. Bindings declared inside a group are scoped to that group, and nested groups can override outer ones for the same parameter name:

```python
async def _public(raw: str) -> Post | None:
    return await Post.where(slug=raw).first()


async def _admin(raw: str) -> Post | None:
    return await Post.with_trashed().where(id=raw).first()


with Route.group(prefix="/v1"):
    Route.bind("post", _public)

    @Route.get("/posts/{post}")
    async def show(post: Post) -> dict[str, str]:
        return {"id": post.id}

    with Route.group(prefix="/admin"):
        Route.bind("post", _admin)  # overrides _public for nested routes

        @Route.get("/posts/{post}")
        async def admin_show(post: Post) -> dict[str, str]:
            return {"id": post.id}
```

### What's actually happening

Arvel inspects the handler signature when the route mounts, replaces each `Model`-typed parameter (or parameter that has a registered resolver) with a `str` in the FastAPI-visible signature, then runs the lookup at request time before delegating to the handler. The binder is exported as `ImplicitRouteModelBinder` if you need to introspect it from your own code or tests; the default instance is registered automatically by `Router.register_with_app`.

```python
from arvel.routing import ImplicitRouteModelBinder

binder = ImplicitRouteModelBinder()
binder.model_parameters(show)
# {'article': <class 'Article'>}
```

Because the binder needs an active database session, every route that uses model binding must run behind the `DatabaseTransaction` middleware (the same one you already use for any handler that touches the DB).

## Named routes

Every route can carry a `name`:

```python
@Route.get("/users/{user_id}", name="users.show")
async def show(user_id: str) -> dict[str, str]: ...
```

Generate URLs from names with the `route()` helper:

```python
from arvel.routing import route

route("users.show", user_id=42)
# → "/users/42"

route("users.show", absolute=True, user_id=42)
# → "https://example.com/users/42"   (when APP_URL=https://example.com)
```

`route()` raises `RouteNotFoundError` when the name isn't registered, and `RoutingError` when a placeholder is missing or `absolute=True` is requested without `APP_URL`.

The `url()` helper turns any relative path into an absolute one against `APP_URL`:

```python
from arvel import url

url("/dashboard")
# → "https://example.com/dashboard"
```

## Route groups

`Route.group(...)` is a context manager that applies common attributes to every route registered inside its block: a path prefix, middleware, and a name prefix.

```python
from arvel import Route, Authenticate, Throttle, InMemoryStore


with Route.group(
    prefix="/api",
    middleware=[Authenticate("api"), Throttle(60, store=InMemoryStore())],
    name_prefix="api.",
):
    @Route.get("/me", name="me")
    async def me() -> dict[str, str]:
        return {"name": "you"}
    # Route name: api.me
```

Groups can nest. Middleware stacks combine outer-then-inner. Prefixes concatenate. Name prefixes concatenate.

```python
with Route.group(prefix="/api", name_prefix="api."):
    with Route.group(prefix="/v1", middleware=[Throttle(60)], name_prefix="v1."):
        @Route.get("/users", name="users.index")
        async def index(): ...
        # Final URL:  /api/v1/users
        # Final name: api.v1.users.index
```

`name_prefix` only affects routes that declare a `name=`. Anonymous routes stay anonymous.

## Signed URLs

For tamper-proof, optionally time-limited links — typical for email verification or password reset — use `URL.signed_route()`:

```python
from datetime import UTC, datetime, timedelta
from arvel.routing import URL

# 24-hour-valid link
URL.signed_route(
    "verify-email",
    expires_at=datetime.now(UTC) + timedelta(hours=24),
    user_id=5,
)
# → "https://example.com/verify/5?expires=1748102400&signature=Xy3K..."
```

The signature is HMAC-SHA256 over the path and query string, keyed off `APP_KEY` (Laravel-compatible — `base64:<...>` is accepted, as is bare base64). `expires_at` accepts a timezone-aware `datetime` or a Unix timestamp `int`. Naive datetimes are rejected outright.

Two ways to verify in a handler:

```python
from arvel.routing import URL
from fastapi import Request


# 1. Manual check inside the handler
@Route.get("/verify/{user_id}", name="verify-email")
async def verify(user_id: int, request: Request) -> dict[str, bool]:
    return {"valid": URL.has_valid_signature(request)}


# 2. Middleware that aborts with 403 on a bad signature
from arvel.http.middleware import SignedMiddleware

with Route.group(middleware=[SignedMiddleware()]):
    @Route.get("/verify/{user_id}", name="verify-email")
    async def verify(user_id: int) -> dict[str, int]:
        return {"verified": user_id}
```

Tampering with any signed query param or path segment makes `has_valid_signature` return `False`. Expired URLs (past `expires`) likewise fail verification — the `expires` value is part of the signed payload so it can't be extended after the fact.

## HTML form method spoofing

HTML `<form>` can only emit GET and POST. To target a `PUT`/`PATCH`/`DELETE` route from a server-rendered form, include a hidden `_method` field and mount `MethodSpoofMiddleware`:

```html
<form action="/items/5" method="POST">
    <input type="hidden" name="_method" value="PUT">
    <!-- ... fields ... -->
</form>
```

```python
from arvel.http.middleware import MethodSpoofMiddleware

app.add_middleware(MethodSpoofMiddleware)
```

Only POST requests with a form Content-Type are inspected. JSON bodies pass through untouched. Unknown `_method` values (anything other than `PUT`, `PATCH`, `DELETE`) are ignored.

## Route service providers

If you have many routes, a `RouteServiceProvider` keeps registration tidy:

```python
from arvel import RouteServiceProvider, Route, Router


class AppRoutes(RouteServiceProvider):
    def map_routes(self, router: Router) -> None:
        with Route.group(prefix="/api"):
            @Route.get("/health")
            async def health() -> dict[str, bool]:
                return {"ok": True}
```

Register the provider with your `Application` and `boot()` will call `map_routes(router)` for you.

## Where to next?

- [Middleware](middleware.md) — the request pipeline.
- [Controllers](controllers.md) — class-based handlers.
- [Requests](requests.md) — typed input validation.
- [Responses](responses.md) — returning data.
