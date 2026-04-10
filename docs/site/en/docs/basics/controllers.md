# Controllers

Controllers bundle related HTTP actions on a class: shared dependencies, a URL prefix, OpenAPI tags, and optional default middleware. Arvel resolves controller instances from the **request-scoped** DI container when `RequestContainerMiddleware` is active, so constructors can ask for database sessions, config, or domain services the same way route callables can.

## `BaseController`

Subclass `BaseController` and set class attributes for defaults:

- `prefix`: path segment before each route path (for example `"posts"`)
- `tags`: OpenAPI tags applied when not overridden per method
- `description`: optional class-level OpenAPI description
- `middleware`: tuple of middleware **aliases** inherited by every route unless overridden

```python
from arvel.http import BaseController, route


class PostController(BaseController):
    prefix = "posts"
    tags = ("Posts",)
    middleware = ("throttle",)

    @route.get("/", name="index")
    async def index(self) -> dict[str, str]:
        return {"message": "list"}

    @route.get("/{post_id}", name="show")
    async def show(self, post_id: int) -> dict[str, int]:
        return {"post_id": post_id}
```

## Route decorators

The `route` object exposes `get`, `post`, `put`, `patch`, and `delete`. Each attaches metadata (`ControllerRouteMeta`) to the method: HTTP verb, path, optional `name`, per-route `middleware` / `without_middleware`, and any extra FastAPI kwargs (response model, deprecated flag, and so on).

Do not pass `methods=` yourself—the decorator sets it.

```python
@route.post("/", name="store", middleware=["csrf"])
async def store(self, payload: CreatePostPayload) -> dict[str, str]:
    ...
```

## Registering a controller on the router

Call `router.controller(PostController)` on your `Router`. Arvel walks declared methods, builds FastAPI endpoints that resolve the controller instance per request, merges tags and `operation_id`, and—unless `include_resource_actions=False`—also registers conventional resource actions (`index`, `store`, …) when those methods exist and were not already declared with `@route`.

Default route names look like `{controller_snake}.{method}` where `UserController` becomes `user`.

## Dependency injection with `Inject`

Use `Inject(Interface)` as a **default value** for parameters. FastAPI treats it as `Depends`, while static analysis still sees the real type inside the method body.

```python
from arvel.http import BaseController, Inject, route
from myapp.services import PostService


class PostController(BaseController):
    @route.get("/{post_id}")
    async def show(
        self,
        post_id: int,
        posts: PostService = Inject(PostService),
    ) -> dict[str, str]:
        return {"title": await posts.title_for(post_id)}
```

Resolution uses `request.state.container` when present; otherwise Arvel falls back to instantiating the controller without container support.

## `resolve_controller`

When you prefer function-based endpoints but still want a controller-shaped dependency, `resolve_controller(MyController)` returns a FastAPI dependency that resolves `MyController` from the container (or constructs it). That pairs well with hybrid apps that mix bare functions and class controllers.

## Resource-style controllers

If you skip explicit `@route` decorators for CRUD, ensure methods named `index`, `store`, `show`, `update`, and `destroy` exist when you rely on automatic resource registration. Alternatively call `router.resource("posts", PostController)` to map REST paths and names without repeating paths manually.

## Practical notes

- Instance methods need a `Request` in the resolved signature for container wiring unless you only use path/query/body parameters—Arvel injects `Request` when building the proxy if you omitted it but need DI.
- Keep controllers thin: validate with `FormRequest`, delegate to services injected via `Inject`, and return `JsonResource` or plain dicts for JSON helpers.
