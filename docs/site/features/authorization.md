# Authorization

<a name="introduction"></a>
## Introduction

In addition to [authentication](authentication.md), Arvel provides a way to authorize user actions against a given resource. Authorization is built on two primitives: **gates** (closures that decide a single ability) and **policies** (classes that group authorization logic around a model).

> [!NOTE]
> Authorization in Arvel is deliberately minimal — a `Gate` class, a `Policy` base, and a `CanMiddleware`. There is no `Gate` facade and no `Auth.user()`-style implicit user; you pass the user explicitly. Roles and permissions are not in core (see [Roles & Permissions](#roles-and-permissions)).

<a name="quick-start"></a>
### Quick start

The `Gate` singleton is bound by [`AuthServiceProvider`](authentication.md#registering-the-provider). Define abilities in a provider's `boot()`, then authorize in a handler or attach [`CanMiddleware`](#enforcing-authorization-in-routes):

```python
from typing import Any

from starlette.requests import Request

from arvel.auth.gate import Gate
from arvel.auth.policy import Policy
from arvel.providers import ServiceProvider
from app.models.post import Post


class AuthorizationServiceProvider(ServiceProvider):
    async def boot(self) -> None:
        gate = self.container.make(Gate)
        gate.define("edit-post", lambda user, post: user.id == post.user_id)
        gate.policy(Post, PostPolicy())


class PostPolicy(Policy[Post]):
    def update(self, user: Any, post: Post) -> bool:
        return post.user_id == user.id


async def update_post(request: Request, post: Post) -> dict[str, str]:
    gate = request.app.state.arvel_container.make(Gate)
    user = request.state.user
    await gate.authorize("update", user, post)
    post.title = (await request.json())["title"]
    await post.save()
    return {"status": "ok"}
```

Route middleware for abilities that don't need a loaded model:

```python
from starlette.requests import Request

from arvel import Route
from arvel.auth.middleware.can import CanMiddleware
from arvel.http.middleware import Authenticate


@Route.get(
    "/admin",
    middleware=[Authenticate("web"), CanMiddleware("admin-only")],
)
async def admin(request: Request) -> dict[str, str]:
    return {"area": "admin"}
```

| Pattern | When to use |
|---|---|
| `gate.define(...)` | One-off ability with a closure |
| `gate.policy(Model, Policy())` | CRUD-style rules grouped on a model |
| `CanMiddleware("ability", model_param="id")` | Enforce at the route; passes the path param as the resource argument |
| Role / permission tables | [`arvel-permission`](../packages/permission.md) |

<a name="registering-the-provider"></a>
## Registering the Provider

There's no separate authorization provider — the `Gate` singleton is bound by `AuthServiceProvider`, the same provider that powers [authentication](authentication.md). Add it to `bootstrap/providers.py`:

```python
# bootstrap/providers.py
from arvel.auth.provider import AuthServiceProvider

providers = [
    # ...other providers...
    AuthServiceProvider,
]
```

Without it, `self.container.make(Gate)` raises because nothing has registered the binding.

<a name="gates"></a>
## Gates

The `Gate` is registered as a container singleton. Resolve it from the container (or inject it) to define and check abilities.

<a name="defining-abilities"></a>
### Defining Abilities

Define an ability with a name and a callback. The callback receives the user and any resource arguments, and returns a boolean. It can be sync or async. Resolve the `Gate` singleton from the container — typically in a service provider's `boot()`, where `self.container` is available:

```python
from arvel.auth.gate import Gate
from arvel.providers import ServiceProvider


class AuthorizationServiceProvider(ServiceProvider):
    async def boot(self) -> None:
        gate = self.container.make(Gate)
        gate.define("edit-post", lambda user, post: user.id == post["owner_id"])
```

The snippets below assume `gate` is that resolved instance.

<a name="authorizing-actions"></a>
### Authorizing Actions

Three async methods check an ability:

```python
from arvel.auth.exceptions import AuthorizationException

if await gate.allows("edit-post", user, post):
    ...

if await gate.denies("edit-post", user, post):
    raise AuthorizationException()

# raises AuthorizationException when denied
await gate.authorize("edit-post", user, post)
```

> [!WARNING]
> Gates are **fail-closed**: checking an ability that was never defined (and has no matching policy) raises `AuthorizationException` rather than silently returning `False`. Define every ability you check.

<a name="before-and-after-hooks"></a>
### Before & After Hooks

Register a `before` hook to short-circuit checks (for example, to grant superadmins everything). A non-`None` return value wins. An `after` hook observes the result:

```python
gate.before(lambda user, ability: True if user.is_admin else None)
gate.after(lambda user, ability, result: log_decision(user, ability, result))
```

> [!NOTE]
> `before` hooks receive only `(user, ability)` — they can't inspect the resource arguments. Use a full ability or policy when the decision depends on the resource.

<a name="policies"></a>
## Policies

When authorization logic for a model grows beyond a single closure, group it into a policy class.

<a name="writing-a-policy"></a>
### Writing a Policy

Subclass `Policy[T]`. Each ability maps to a method of the same name, receiving the user and (optionally) the resource. Methods can be sync or async:

```python
from typing import Any
from arvel.auth.policy import Policy
from app.models.post import Post


class PostPolicy(Policy[Post]):
    def view(self, user: Any, post: Post) -> bool:
        return post.published or post.user_id == user.id

    async def update(self, user: Any, post: Post) -> bool:
        return post.user_id == user.id
```

<a name="registering-a-policy"></a>
### Registering a Policy

Map a model type to a policy instance on the gate. The gate dispatches to the policy automatically when the first resource argument's type is registered:

```python
gate.policy(Post, PostPolicy())

await gate.allows("update", user, post)   # routed to PostPolicy.update
```

> [!NOTE]
> There is no policy auto-discovery — register each policy explicitly. The ability name must exactly match the policy method name.

<a name="policy-filters"></a>
### Policy Filters

Add a `before` method to authorize (or deny) every ability on a policy before its per-ability methods run. Return `True` to grant all, `False` to deny all, or `None` to fall through to the ability method — the same semantics as Laravel's policy filters. Most often used to let administrators do anything, or to lock out a banned user:

```python
class PostPolicy(Policy[Post]):
    def before(self, user: Any, ability: str) -> bool | None:
        if user.role == "admin":
            return True
        return None

    async def update(self, user: Any, post: Post) -> bool:
        return post.user_id == user.id
```

`before` runs after a gate-level `before` hook and before the matching ability method, on both `gate.allows(...)` and `Policy.check(...)`.

<a name="enforcing-authorization-in-routes"></a>
## Enforcing Authorization in Routes

Attach `CanMiddleware` to require an ability. It checks the gate for the authenticated user and raises an unauthenticated error (401) when no user is present, or an authorization error (403) when the check fails:

```python
from starlette.requests import Request

from arvel import Route
from arvel.auth.middleware.can import CanMiddleware
from arvel.http.middleware import Authenticate


@Route.get(
    "/admin",
    middleware=[Authenticate("web"), CanMiddleware("admin-only")],
)
async def admin(request: Request) -> dict[str, str]:
    return {"area": "admin"}
```

Pass `model_param=` to inject a route path parameter as the gate's resource argument.

<a name="roles-and-permissions"></a>
## Roles & Permissions

Core Arvel ships gates, policies, and `CanMiddleware` — but **no roles or permissions tables**. Role-based access control lives in the separate **`arvel-permission`** package, which adds `Role` and `Permission` models, `HasRoles` / `HasPermissions` traits, route middleware (`RoleMiddleware`, `PermissionMiddleware`), and a gate integration that grants abilities based on a user's permissions.

See [arvel-permission](../packages/permission.md).
