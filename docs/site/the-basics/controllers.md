# Controllers

<a name="introduction"></a>
## Introduction

Instead of defining all request-handling logic as standalone functions in your route files, you may group related handling into "controller" classes. A controller can group related request handling logic into a single class — for example, a `UserController` class might handle all incoming requests related to users: showing, creating, updating, and deleting users.

Controllers are entirely optional. A plain `async def` route handler is perfectly fine for simple endpoints. Reach for a controller when a route file grows unwieldy, or when several handlers share dependencies you'd rather inject once.

Every controller in Arvel is resolved through the [service container](../core-concepts/service-container.md), so its constructor dependencies are wired automatically.

<a name="writing-controllers"></a>
## Writing Controllers

<a name="basic-controllers"></a>
### Basic Controllers

A controller extends the base `Controller` class and defines one `async def` method per action. Bind each method to a route with the `controller` and `action` keywords:

```python
from arvel.http.controller import Controller
from arvel.routing import Route
from app.models.user import User


class UserController(Controller):
    async def show(self, user: User) -> dict:
        return user.to_dict()


Route.get("/api/users/{user}", controller=UserController, action="show", name="users.show")
```

A controller method behaves exactly like a route handler function. Its parameters are resolved the same way: path and query parameters from the URL, request bodies from Pydantic models, the `Request` object on demand, [route model binding](routing.md#route-model-binding) for model-typed parameters, and [container services](#method-injection) via `dep(...)`.

```python
class UserController(Controller):
    async def index(self) -> list[dict]:
        users = await User.all()
        return [u.to_dict() for u in users]

    async def show(self, user: User) -> dict:   # model binding resolves `user`
        return user.to_dict()


Route.get("/api/users", controller=UserController, action="index", name="users.index")
Route.get("/api/users/{user}", controller=UserController, action="show", name="users.show")
```

> [!NOTE]
> The base `Controller` class is a lightweight marker — it has no middleware property or authorization helpers. Attach [middleware](middleware.md) on the route or [route group](routing.md#route-groups), and perform authorization with a [form request](validation.md#form-request-validation) or a [gate](../features/authorization.md).

<a name="single-action-controllers"></a>
### Single Action Controllers

If a controller action is particularly complex, you might find it convenient to dedicate an entire controller class to that single action. Define a `__call__` method and bind the route with only `controller` (no `action`):

```python
from arvel import Controller, Route
from starlette.requests import Request


class ProvisionServer(Controller):
    async def __call__(self, request: Request) -> dict:
        # ... provision a server ...
        return {"status": "provisioning"}


Route.post("/api/servers", controller=ProvisionServer)
```

> [!WARNING]
> Binding `controller=` without `action=` requires the class to define `__call__`. If it doesn't, route registration raises a `TypeError` immediately, at decoration time — not at request time.

<a name="controller-dependency-injection"></a>
## Controller Dependency Injection

<a name="constructor-injection"></a>
### Constructor Injection

The [service container](../core-concepts/service-container.md) resolves all controllers, so you may type-hint any dependencies your controller needs in its constructor. The declared dependencies are resolved and injected automatically:

```python
class UserController(Controller):
    def __init__(self, users: UserService) -> None:
        self.users = users

    async def index(self) -> list[dict]:
        return await self.users.all()
```

> [!NOTE]
> Controllers are resolved from the container **fresh on every request**, like in Laravel — so it's safe to store per-request state on `self` without it leaking to the next request. Constructor dependencies registered as `singleton()` (or `instance()`) are still shared across those per-request controllers; only the controller shell is new each time. If you deliberately want one shared controller instance, bind the controller itself as a `singleton()` / `instance()`.

<a name="method-injection"></a>
### Method Injection

In addition to constructor injection, you may resolve container services directly in an action's signature with `dep(...)`. This pulls the service from the per-request [scope](../core-concepts/service-container.md):

```python
from arvel import Controller, dep
from fastapi import Depends


class ReportController(Controller):
    async def export(self, reports: ReportService = Depends(dep(ReportService))) -> dict:
        return await reports.export()
```

`dep(...)` returns a resolver; wrap it in FastAPI's `Depends(...)` so the service is resolved per request rather than the function object being used as the default.

The `Request` instance is injected by type-hinting a parameter with it, exactly as in a function handler:

```python
class SessionController(Controller):
    async def store(self, request: Request) -> dict:
        ...
```

<a name="resource-controllers"></a>
## Resource Controllers

Think of each ORM model in your application as a "resource", and the typical set of actions you perform against it — list, create, show, update, delete — as repetitive. Resource routing assigns those conventional routes to a controller with a single line of code. See [Resource Routes](routing.md#resource-routes) for the routing side:

```python
from app.http.controllers.post_controller import PostController

Route.resource("/api/posts", PostController)
```

<a name="actions-handled-by-a-resource-controller"></a>
### Actions Handled by a Resource Controller

`Route.resource` expects your controller to implement methods named after the seven resource actions:

| Verb | Path | Method | Purpose |
|---|---|---|---|
| GET | `/api/posts` | `index` | List the resource |
| GET | `/api/posts/create` | `create` | Show the create form |
| POST | `/api/posts` | `store` | Persist a new resource |
| GET | `/api/posts/{post}` | `show` | Show one resource |
| GET | `/api/posts/{post}/edit` | `edit` | Show the edit form |
| PUT | `/api/posts/{post}` | `update` | Persist changes |
| DELETE | `/api/posts/{post}` | `destroy` | Delete the resource |

The member routes (`show`, `edit`, `update`, `destroy`) receive the resource via [model binding](routing.md#route-model-binding) when you type-hint the parameter:

```python
from arvel import Controller
from app.http.requests import StorePostRequest, UpdatePostRequest
from app.models.post import Post


class PostController(Controller):
    async def index(self) -> list[dict]:
        return [p.to_dict() for p in await Post.all()]

    async def store(self, form: StorePostRequest) -> dict:
        post = await Post.create(**form.validated().model_dump())
        return post.to_dict()

    async def show(self, post: Post) -> dict:
        return post.to_dict()

    async def update(self, post: Post, form: UpdatePostRequest) -> dict:
        post.fill(**form.validated().model_dump())
        await post.save()
        return post.to_dict()

    async def destroy(self, post: Post) -> dict:
        await post.delete()
        return {"deleted": True}
```

<a name="api-resource-controllers"></a>
### API Resource Controllers

When building a JSON API, the `create` and `edit` actions — which exist to render HTML forms — are dead weight. Use `Route.api_resource` to register the resource routes **without** them:

```python
Route.api_resource("/api/posts", PostController)
# index, store, show, update, destroy
```

You can further narrow, rename, or scope a resource registration — see [Partial Resource Routes](routing.md#partial-resource-routes).

<a name="generating-controllers"></a>
## Generating Controllers

The `make:controller` command scaffolds a controller in `app/http/controllers/`. The class name is completed for you — `make:controller Post` and `make:controller PostController` both produce `PostController`:

```bash
arvel make:controller Post
```

| Flag | Effect |
|---|---|
| `--force` | Overwrite an existing file. |
| `--resource` | Generate stubs for all seven REST actions. |
| `--api` | With `--resource`, omit the `create` and `edit` actions. |
| `--model` | Generate the companion model (derived from the controller name) and, under `--resource`, import it and type the member parameters. |
| `--model-name Article` | Same as `--model`, but use this model name instead of the derived one. |
| `--observer` | Also generate the matching `Observer`. |
| `--policy` | Also generate the matching `Policy`. |
| `--requests` | Also generate the `Store…Request` / `Update…Request` pair. |

```bash
arvel make:controller Post --resource
arvel make:controller Post --resource --api
arvel make:controller Post --resource --model
arvel make:controller Post --resource --model --observer --policy --requests
```

That last command scaffolds `PostController`, the `Post` model, `PostObserver`, `PostPolicy`, and `StorePostRequest` / `UpdatePostRequest` in one shot. Companions that already exist are skipped, not overwritten.

> [!NOTE]
> The generated resource actions raise `NotImplementedError` until you fill them in — they're stubs, not working endpoints.

<a name="responses-and-redirects"></a>
## Responses & Redirects

A handler can return a `dict`, a list, a Pydantic model, or any Starlette `Response` and it just works. For the cases where you want to set a status, build a redirect, or flash to the session, Arvel ships Laravel-style `response()` and `redirect()` helpers.

<a name="the-response-helper"></a>
### The `response()` Helper

`response()` returns a builder for the common shapes:

```python
from arvel.http import response

response().json({"id": 1}, status=201)        # JSONResponse
response().text("pong")                          # text/plain
response().make(b"raw bytes", headers={"X-K": "v"})
response().no_content()                           # 204, empty body
```

<a name="redirects"></a>
### Redirects

`redirect()` builds a redirect response. Point it at a path, a named route, or send the user back where they came from:

```python
from arvel.http import back, redirect, to_route

redirect("/dashboard")                  # 302 to a path
redirect("/dashboard", status=301)      # permanent
to_route("users.show", id=7)            # resolves the named route -> /users/7
back(request, fallback="/")             # uses the Referer header
```

<a name="redirects-with-flashed-session-data"></a>
### Redirecting With Flashed Session Data

Chain `.with_(request, ...)` to flash values into the session before redirecting. They're readable on the **next** request — the usual post-action pattern. This needs the [session middleware](../features/session.md) active on the route; without it, `.with_()` is a no-op.

```python
async def store(self, form: StorePostRequest, request: Request) -> Redirect:
    await Post.create(**form.validated().model_dump())
    return redirect("/posts").with_(request, status="Post created!")
```

On the next request, read it back with `request.state.session.get("status")`.
