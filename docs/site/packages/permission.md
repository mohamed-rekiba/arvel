# arvel-permission

<a name="introduction"></a>
## Introduction

`arvel-permission` adds roles and permissions to Arvel. It gives you `Role` and `Permission` models, `HasRoles` / `HasPermissions` mixins for your user model, route middleware, and a bridge into the authorization [`Gate`](../features/authorization.md).

<a name="a-quick-tour"></a>
## A Quick Tour

Install, migrate, mix the traits into `User`, then assign and check:

```bash
uv add "arvel[permission]"
arvel vendor:publish --tag=arvel-permission
arvel migrate
```

```python
from typing import ClassVar
from arvel.database import Model, id_
from arvel.database.orm import MorphToMany
from arvel_permission import HasRoles, HasPermissions, Role, Permission
from arvel_permission import model_has_roles, model_has_permissions


class User(Model, HasRoles, HasPermissions):
    __tablename__ = "users"
    id: int = id_(init=False)
    default_guard_name: ClassVar[str] = "web"

    roles: ClassVar[MorphToMany[Role]] = MorphToMany(
        Role, table=model_has_roles, name="model", related_key="role_id"
    )
    permissions: ClassVar[MorphToMany[Permission]] = MorphToMany(
        Permission, table=model_has_permissions, name="model", related_key="permission_id"
    )
```

```python
await user.assign_role("editor")
await user.give_permission_to("posts.publish")

if await user.has_permission_to("posts.publish"):
    ...
```

Protect a route:

```python
@app.get("/admin/posts", middleware=["permission:posts.publish"])
async def publish_post(request):
    ...
```

<a name="installation"></a>
## Installation

```bash
uv add "arvel[permission]"
```

Register the provider and publish the migration:

```python
# bootstrap/providers.py
from arvel_permission import PermissionServiceProvider

providers = [PermissionServiceProvider]
```

```bash
arvel vendor:publish --tag=arvel-permission
arvel migrate
```

The migration creates five tables: `roles`, `permissions`, `model_has_roles`, `model_has_permissions`, `role_has_permissions`.

<a name="making-a-model-rolable"></a>
## Making a Model Rolable

Mix `HasRoles` and `HasPermissions` into your user model and declare the polymorphic pivots:

```python
from typing import ClassVar
from arvel.database import Model, id_
from arvel.database.orm import MorphToMany
from arvel_permission import (
    HasRoles, HasPermissions, Role, Permission,
    model_has_roles, model_has_permissions,
)


class User(Model, HasRoles, HasPermissions):
    __tablename__ = "users"
    id: int = id_(init=False)
    default_guard_name: ClassVar[str] = "web"

    roles: ClassVar[MorphToMany[Role]] = MorphToMany(
        Role, table=model_has_roles, name="model", related_key="role_id"
    )
    permissions: ClassVar[MorphToMany[Permission]] = MorphToMany(
        Permission, table=model_has_permissions, name="model", related_key="permission_id"
    )
```

> [!NOTE]
> All trait methods are async and need an active DB session in scope (the framework's session context). In a request that's already set up for you; in scripts and tests, wrap the call in `DB.transaction()`.

<a name="seeding-roles-and-permissions"></a>
## Seeding Roles & Permissions

Use `PermissionRegistrar` to find-or-create roles and permissions. Pass a session for DB-backed registration:

```python
from arvel.database.db import DB
from arvel_permission import PermissionRegistrar, Role, Permission


async with DB.transaction() as session:
    registrar = PermissionRegistrar(session)

    editor = await registrar.a_register_role("editor")
    publish = await registrar.a_register_permission("posts.publish")

    await editor.permissions.sync([publish.id])
```

For tests and REPL exploration, construct without a session — roles and permissions live in memory:

```python
registrar = PermissionRegistrar()
editor = registrar.register_role("editor")
publish = registrar.register_permission("posts.publish")
```

The provider does **not** container-bind `PermissionRegistrar` — instantiate it where you need it (seeders, CLI commands, tests).

<a name="assigning-and-checking"></a>
## Assigning & Checking

```python
await user.assign_role("editor")
await user.give_permission_to("posts.publish")

await user.has_role("editor")                    # -> bool
await user.has_any_role("editor", "admin")
await user.has_all_roles("editor", "reviewer")
await user.has_permission_to("posts.publish")
await user.has_any_permission("posts.edit", "posts.publish")
await user.has_all_permissions("posts.edit", "posts.publish")

names = await user.get_role_names()
perms = await user.get_permission_names()
direct = await user.get_direct_permissions()     # not via roles
via_roles = await user.get_permissions_via_roles()
all_perms = await user.get_all_permissions()     # direct + via roles
```

Replace a user's grants wholesale with `sync_*`:

```python
await user.sync_roles(["editor", "reviewer"])           # detach the rest
await user.sync_permissions(["posts.edit"])             # replace direct perms
await user.remove_role("editor")
await user.revoke_permission_to("posts.publish")
```

Permissions resolve through roles automatically — `has_permission_to` is true if the user has the permission directly **or** via any assigned role.

`has_level(minimum)` compares the user's highest role `level` against a threshold — useful for "only admins and above can manage roles":

```python
if await user.has_level(100):
    await target.sync_roles(["viewer"])   # still enforce policy yourself
```

### Querying models by role or permission

Class-level helpers return every instance that does (or doesn't) hold a role or permission:

```python
async with DB.transaction() as session:
    admins = await User.query_with_role("admin", session=session)
    others = await User.query_without_role("admin", session=session)
    editors = await User.query_with_permission("posts.edit", session=session)
```

These match on the same morph token the pivot stores, so they work whether you rely on the short-class-name default or register a `morph_map`/`__morph_class__` alias. (`query_without_*` is the complement — it returns the rows that don't hold the grant.)

> [!WARNING]
> `give_permission_to`, `revoke_permission_to`, `assign_role`, and `remove_role` are
> primitives — they do **not** check the acting user's own authority. An admin endpoint
> that exposes them must enforce policy itself, or a user who can manage roles could grant
> themselves abilities they don't hold (privilege escalation). The rule the e-commerce kit
> follows: you can only grant or revoke a permission you hold, and only manage a role at or
> below your own level.

<a name="wildcard-permissions"></a>
## Wildcard Permissions

With `wildcard_enabled` (the default), a held permission like `posts.*` satisfies a check for `posts.edit`.

```python
await role.sync_permissions([Permission(name="posts.*")])
await user.assign_role(role)
await user.has_permission_to("posts.publish")   # True
```

<a name="route-middleware"></a>
## Route Middleware

The package provides three middleware classes. Register them on your router — the provider does not wire them automatically:

```python
from arvel_permission import RoleMiddleware, PermissionMiddleware, RoleOrPermissionMiddleware

router.middleware("role", RoleMiddleware)
router.middleware("permission", PermissionMiddleware)
router.middleware("role_or_permission", RoleOrPermissionMiddleware)
```

Then protect routes with the middleware string form:

```python
@app.get("/admin", middleware=["role:admin"])
async def admin_panel(request):
    ...

@app.get("/posts/publish", middleware=["permission:posts.publish"])
async def publish(request):
    ...

@app.get("/dashboard", middleware=["role:admin|manager"])
async def dashboard(request):
    ...

@app.get("/moderate", middleware=["role_or_permission:moderator|posts.edit"])
async def moderate(request):
    ...
```

Pipe-separated values mean OR — `admin|manager` passes if the user holds either role. Middleware reads the authenticated user from `request.state.user` (set by your auth middleware). A failed check raises `UnauthorizedException` — 401 when no user, 403 when the user lacks access.

<a name="gate-integration"></a>
## Gate Integration

When `PermissionServiceProvider` boots and a `Gate` is bound, it registers a `before` hook so permission-shaped abilities resolve through the user's grants:

```python
await gate.allows("posts.edit", user)   # True when user.has_permission_to("posts.edit")
```

You can also wire it manually:

```python
from arvel_permission import register_permissions_with_gate

register_permissions_with_gate(gate, guard="web")
```

The hook returns `True` when the user holds the ability as a permission, and `None` otherwise — letting explicit `gate.define` policies handle abilities that aren't permission-shaped. If no `Gate` is bound at boot, the provider skips this silently.

<a name="configuration"></a>
## Configuration

`PermissionConfig` is a plain (frozen) model — there are **no environment variables**. Override defaults by subclassing the provider:

```python
from arvel_permission import PermissionConfig, PermissionServiceProvider


class AppPermissionProvider(PermissionServiceProvider):
    config = PermissionConfig(default_guard_name="api", wildcard_enabled=True)
```

Notable fields: `default_guard_name` (`web`), `cache_enabled` (`true`), `wildcard_enabled` (`true`), `events_enabled` (`false`), `cache_ttl` (`86400`).

Checking a role/permission that belongs to a different guard raises `GuardMismatchError` — pass `guard=` explicitly when your app uses multiple guards:

```python
await user.has_role("api-admin", guard="api")
```

<a name="gotchas"></a>
## Gotchas

- The provider binds only `PermissionConfig`. `PermissionRegistrar` is not container-bound — instantiate it directly if you need programmatic role/permission registration.
- Middleware and the user-model mixins are wired by you, not by the provider.
- Checking a role/permission that belongs to a different guard raises `GuardMismatchError`.
- The events module is in-process only and off by default (`events_enabled`).
