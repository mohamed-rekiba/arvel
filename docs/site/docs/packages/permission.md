# arvel-permission

<a name="introduction"></a>
## Introduction

`arvel-permission` adds roles and permissions to Arvel. It gives you `Role` and `Permission` models, `HasRoles` / `HasPermissions` mixins for your user model, route middleware, and a bridge into the authorization [`Gate`](../features/authorization.md).

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
> All trait methods are async and need an active DB session in scope (the framework's session context). In a request that's already set up for you; in scripts and tests, wrap the call in the session context.

<a name="assigning-and-checking"></a>
## Assigning & Checking

```python
await user.assign_role("editor")
await user.give_permission_to("posts.publish")

await user.has_role("editor")              # -> bool
await user.has_any_role("editor", "admin")
await user.has_permission_to("posts.publish")
names = await user.get_role_names()
```

Other methods: `remove_role`, `sync_roles`, `has_all_roles`, `has_level`, `revoke_permission_to`, `sync_permissions`, `get_all_permissions`, `get_direct_permissions`, `get_permissions_via_roles`.

Permissions resolve through roles automatically — `has_permission_to` is true if the user has the permission directly **or** via any assigned role.

### Querying models by role or permission

Class-level helpers return every instance that does (or doesn't) hold a role or permission:

```python
admins   = await User.query_with_role("admin", session=session)
others   = await User.query_without_role("admin", session=session)
editors  = await User.query_with_permission("posts.edit", session=session)
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

<a name="route-middleware"></a>
## Route Middleware

The package provides three middleware classes. Register them yourself — the provider does not wire them:

```python
from arvel_permission import RoleMiddleware, PermissionMiddleware, RoleOrPermissionMiddleware

RoleMiddleware("admin")
PermissionMiddleware("posts.publish")
RoleOrPermissionMiddleware("admin|posts.publish")   # pipe = OR
```

A failed check raises `UnauthorizedException`.

<a name="gate-integration"></a>
## Gate Integration

When `PermissionServiceProvider` boots and a `Gate` is bound, it registers a `before` hook so `await gate.allows("posts.edit", user)` resolves through the user's permissions. If no `Gate` is bound, this is skipped silently.

<a name="configuration"></a>
## Configuration

`PermissionConfig` is a plain (frozen) model — there are **no environment variables**. Override defaults by setting the provider's `config` before boot:

```python
from arvel_permission import PermissionConfig, PermissionServiceProvider

class AppPermissionProvider(PermissionServiceProvider):
    config = PermissionConfig(default_guard_name="api", wildcard_enabled=True)
```

Notable fields: `default_guard_name` (`web`), `cache_enabled` (`true`), `wildcard_enabled` (`true`), `events_enabled` (`false`), `cache_ttl` (`86400`).

<a name="gotchas"></a>
## Gotchas

- The provider binds only `PermissionConfig`. `PermissionRegistrar` is not container-bound — instantiate it directly if you need programmatic role/permission registration.
- Middleware and the user-model mixins are wired by you, not by the provider.
- Checking a role/permission that belongs to a different guard raises `GuardMismatchError`.
- The events module is in-process only and off by default (`events_enabled`).
