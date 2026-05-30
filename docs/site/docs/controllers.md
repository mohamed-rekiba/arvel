# Controllers

Controllers group related route handlers into a single class. A `UserController` might handle everything for users — list, show, create, update, delete — instead of scattering handlers across route files.

## Writing controllers

A controller is any class that inherits from `arvel.Controller`. Add async methods for each action; register them on routes.

```python
from arvel import Controller, Route


class UserController(Controller):
    async def index(self) -> list[dict]:
        users = await User.get()
        return [u.to_dict() for u in users]

    async def show(self, user_id: int) -> dict:
        user = await User.find_or_fail(user_id)
        return user.to_dict()

    async def store(self, form: StoreUser) -> dict:
        payload = form.validated()
        user = await User.create(**payload.model_dump())
        return user.to_dict()


# Register the routes:
Route.get("/users", controller=UserController, action="index")
Route.get("/users/{user_id}", controller=UserController, action="show")
Route.post("/users", controller=UserController, action="store")
```

The `controller=` / `action=` pair tells the router to instantiate `UserController` through the [container](container.md) and dispatch to the named method. The method's signature flows through as-is, so [implicit model binding](routing.md#route-model-binding), [`FormRequest`](requests.md) payloads, and regular path / query params all work the same as on plain function handlers.

## Resource controllers

For standard CRUD operations, `Route.resource()` registers all seven routes in one call:

```python
Route.resource("/users", UserController)
```

The controller is expected to expose `index`, `create`, `store`, `show`, `edit`, `update`, and `destroy` methods. Implement only what makes sense and restrict the registered set:

```python
Route.resource("/users", UserController).only("index", "show", "store")
Route.resource("/users", UserController).except_("create", "edit")
```

| Action | Verb | URI | Name | Purpose |
|---|---|---|---|---|
| `index` | GET | `/users` | `users.index` | List |
| `create` | GET | `/users/create` | `users.create` | Show create form (HTML) |
| `store` | POST | `/users` | `users.store` | Persist new |
| `show` | GET | `/users/{user}` | `users.show` | Show one |
| `edit` | GET | `/users/{user}/edit` | `users.edit` | Show edit form (HTML) |
| `update` | PUT | `/users/{user}` | `users.update` | Persist update |
| `destroy` | DELETE | `/users/{user}` | `users.destroy` | Delete |

The member-route parameter (`{user}`) is the singular of the resource segment. Arvel handles common English plurals (`/posts` → `{post}`, `/categories` → `{category}`, `/boxes` → `{box}`); override with `parameter=`:

```python
Route.resource("/posts", PostController, parameter="article")
# /posts, /posts/{article}, /posts/{article}/edit, ...
```

Use `route("users.show", user=5)` (see [routing](routing.md#named-routes)) to build URLs without hardcoding paths. Override individual names with `.names({...})`:

```python
Route.resource("/users", UserController).names({"index": "users.list"})
```

### API-only resources

`Route.api_resource()` is a shortcut for JSON-only APIs — it drops the `create` and `edit` HTML-form routes:

```python
Route.api_resource("/users", UserController)
# Registers: index, store, show, update, destroy — five routes.
```

### Composition

Resource registration plays nicely with [route groups](routing.md#route-groups) and middleware:

```python
with Route.group(prefix="/api/v1", middleware=[Authenticate()]):
    Route.api_resource("/users", UserController)
    Route.api_resource("/posts", PostController).only("index", "show")
```

Per-resource middleware passes through too:

```python
Route.resource("/admin/users", UserController, middleware=[Authorize("admin")])
```

## Invokable controllers

For a single-action class, use the invokable pattern:

```python
class Dashboard(Controller):
    async def __call__(self) -> dict[str, str]:
        return {"page": "dashboard"}


Route.get("/dashboard", controller=Dashboard)
```

This works well when you want the controller class to do one job and the action name to match the class name.

## Dependency injection in controllers

Controllers are resolved through the [container](container.md), so constructor parameters are auto-wired:

```python
class UserController(Controller):
    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer

    async def store(self, form: StoreUser) -> dict:
        payload = form.validated()
        user = await User.create(**payload.model_dump())
        await self._mailer.send(WelcomeMail(user))
        return user.to_dict()
```

`Mailer` is resolved from the container when the route handler is invoked. The same applies to invokable controllers — `Route.get("/dashboard", controller=Dashboard)` instantiates `Dashboard` through the container, picking up whatever constructor dependencies it declares.

Under the hood, every controller-bound route goes through `MethodControllerAdapter` (or its invokable sibling) which calls `container.make(cls)` before binding to the handler method. When no container is registered on `app.state.arvel_container`, the adapter falls back to a plain `cls()` call.

## Method-level dependencies

Just like with function handlers, you can declare per-method dependencies via the parameter list:

```python
class UserController(Controller):
    async def show(self, user_id: int, mailer: Mailer = dep(Mailer)) -> dict:
        ...
```

`dep(...)` only works on method parameters that come from the HTTP layer — constructor injection happens at instantiation time and is preferred for services the whole controller needs.

## Middleware on controllers

Apply middleware at the route level — controllers don't carry middleware metadata themselves:

```python
Route.resource("/admin/users", UserController, middleware=[Authenticate(), Authorize("admin")])
```

If you want different middleware per action, register the routes individually instead of using `Route.resource`.

## Scaffolding a resource controller

`make:controller --resource` writes the stubs so you don't have to:

```bash
arvel make:controller PostController --resource
# → app/http/controllers/post_controller.py
```

Each of the seven actions is generated as `raise NotImplementedError`,
which gives you a noisy 500 the first time a route hits an unimplemented
method — easier to spot than a silent `pass`-and-return-None.

For JSON-only resources that you'll bind with `Route.api_resource()`, drop
the HTML form actions:

```bash
arvel make:controller PostController --resource --api
# Generates: index, store, show, update, destroy (5 methods).
```

To pre-wire [implicit model binding](routing.md#route-model-binding), pass
the model name:

```bash
arvel make:controller PostController --resource --model=Post
```

That adds `from app.models.post import Post` and types the member-method
parameter as `post: Post` instead of `id: int`:

```python
async def show(self, post: Post) -> dict[str, Any]:
    raise NotImplementedError

async def update(self, post: Post) -> dict[str, Any]:
    raise NotImplementedError
```

`--api` and `--model` both require `--resource`. The combinations all
produce code that passes `ruff` and `mypy --strict` immediately — no
post-generation cleanup.

## Putting it together

Here's the full flow from scaffold to live routes. Three commands, one registration line.

**Step 1 — scaffold:**

```bash
arvel make:controller PostController --resource --model=Post
# Writes app/http/controllers/post_controller.py with seven typed stubs.
```

The generated file imports `Post` and types the member-method parameter correctly, so implicit model binding kicks in automatically — Arvel fetches the `Post` row from the database before your handler runs, and returns 404 if it's missing.

**Step 2 — register:**

```python
# bootstrap/routes.py
from app.http.controllers.post_controller import PostController
from arvel.routing import Route

Route.resource("/posts", PostController)
```

One call registers all seven CRUD routes with conventional paths (`/posts`, `/posts/{post}`, etc.) and named routes (`posts.index`, `posts.show`, …). Need JSON-only? Swap in `Route.api_resource()`.

**Step 3 — inspect:**

```bash
arvel route:list
```

```
Method  URI                Name           Action                 Middleware
---------------------------------------------------------------------------
GET     /posts             posts.index    PostController#index   -
GET     /posts/create      posts.create   PostController#create  -
POST    /posts             posts.store    PostController#store   -
GET     /posts/{post}      posts.show     PostController#show    -
GET     /posts/{post}/edit posts.edit     PostController#edit    -
PUT     /posts/{post}      posts.update   PostController#update  -
DELETE  /posts/{post}      posts.destroy  PostController#destroy -
```

From here, implement each stub method. The `{post}` parameter is already typed as `Post` in the method signature — you don't write any lookup code.

## Inspecting your routes

After wiring up a few controllers, you can list everything Arvel has registered with `route:list`:

```bash
arvel route:list
```

Output is a five-column table — Method, URI, Name, Action, Middleware:

```
Method  URI               Name           Action                   Middleware
-----------------------------------------------------------------------------
GET     /posts            posts.index    PostController#index     -
GET     /posts/create     posts.create   PostController#create    -
POST    /posts            posts.store    PostController#store     Authenticate
GET     /posts/{post}     posts.show     PostController#show      -
GET     /posts/{post}/edit posts.edit    PostController#edit      -
PUT     /posts/{post}     posts.update   PostController#update    Authenticate
DELETE  /posts/{post}     posts.destroy  PostController#destroy   Authenticate
```

Narrow down to a single domain with `--filter`:

```bash
arvel route:list --filter api      # only routes whose path contains "api"
```

Pipe machine-readable output through `jq` with `--json`:

```bash
arvel route:list --json | jq '.[] | select(.middleware | length == 0)'
```

## Where to next?

- [Routing](routing.md) — how routes are registered.
- [Middleware](middleware.md) — adding middleware to controller routes.
- [Service Container](container.md) — how controllers are resolved.
