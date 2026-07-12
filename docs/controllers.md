# Controllers

For anything beyond a one-off handler, grouping related request logic into a controller class keeps
routes tidy. A controller is a plain class with `async` action methods.

## Basic controllers

```python
# app/controllers/post_controller.py
from arvel.routing import Controller

class PostController(Controller):
    async def index(self, request):
        return await Post.paginate(per_page=20)

    async def show(self, request, post: Post):     # implicit model binding
        return post
```

Point a route at an action:

```python
from arvel import Route

Route.get("/posts", PostController().index, name="posts.index")
Route.get("/posts/{post}", PostController().show, name="posts.show")   # {post} → implicit Post binding
```

## Controller middleware

Attach middleware to a **resource controller's** actions by overriding `middleware()` — return
`ControllerMiddleware` entries (each scopable to specific actions with `only`/`except_`):

```python
from arvel.routing import ControllerMiddleware

class PostController(Controller):
    @classmethod
    def middleware(cls):
        return [
            ControllerMiddleware("auth"),                       # every action
            ControllerMiddleware("throttle:api", only=("store", "update")),
        ]
```

`middleware()` is consulted by `Route.resource`/`api_resource`; for a plain bound-method route,
attach middleware on the route itself (see [Middleware](middleware.md)).

## Resource controllers

A resource controller handles the standard CRUD verbs for an entity. `Route.resource` wires all of
them to a controller in one call — binding **only the actions the controller actually implements**:

```python
Route.resource("posts", PostController)
```

| Verb & URI                     | Action    | Route name       |
|--------------------------------|-----------|------------------|
| `GET /posts`                   | `index`   | `posts.index`    |
| `GET /posts/create`            | `create`  | `posts.create`   |
| `POST /posts`                  | `store`   | `posts.store`    |
| `GET /posts/{post}`            | `show`    | `posts.show`     |
| `GET /posts/{post}/edit`       | `edit`    | `posts.edit`     |
| `PUT/PATCH /posts/{post}`      | `update`  | `posts.update`   |
| `DELETE /posts/{post}`         | `destroy` | `posts.destroy`  |

The path segment is the **singularized resource name** (`posts` → `{post}`), which is exactly the
name [implicit model binding](routing.md) keys on — so `show(self, request, post: Post)` receives
the loaded model, not a raw id.

For a JSON API, drop the HTML-form actions (`create`/`edit`) with `api=True`, and narrow the set
with `only`/`except_`:

```python
Route.resource("posts", PostController, api=True)
Route.resource("posts", PostController, only=["index", "show"])
Route.resource("posts", PostController, except_=["destroy"])
```

## Authorizing resource actions

Bind a policy to a resource controller so each action is authorization-checked against its
route-bound model (see [Authorization](auth/authorization.md)). The declarative form is preferred:

```python
class PostController(Controller):
    __resource_policy__ = Post          # index/show/... checked against PostPolicy
```

A denied action returns `403` before the action body runs.

## Generating controllers

```bash
arvel make:controller PostController          # a plain controller
arvel make:controller PostController -r       # a resource controller (stubbed actions)
arvel make:controller PostController --api    # a resourceful API controller
```
