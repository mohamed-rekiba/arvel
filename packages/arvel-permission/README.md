# arvel-permission

<p>
<a href="https://pypi.org/project/arvel-permission/">
    <img src="https://img.shields.io/pypi/v/arvel-permission?color=%2334D058" alt="PyPI">
</a>
<img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License">
</p>

Roles and permissions for [Arvel](https://arvel.dev) — a Python port of
[spatie/laravel-permission](https://spatie.be/docs/laravel-permission/v7/introduction) v7.

> **Status**: Pre-alpha.

---

**Documentation**: <a href="https://arvel.dev/packages/permission" target="_blank">https://arvel.dev/packages/permission</a>

---

## Install

```bash
uv add arvel-permission
# or: pip install arvel-permission
```

Register the provider in `bootstrap/providers.py`:

```python
from arvel_permission import PermissionServiceProvider

providers = [
    # ...other providers...
    PermissionServiceProvider,
]
```

Run the migration (adds `roles`, `permissions`, `model_has_roles`, `model_has_permissions`, and
`role_has_permissions`):

```bash
arvel migrate
```

## Make a model role-aware

Mix in `HasRoles` and `HasPermissions`, and wire the polymorphic relations:

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

> All trait methods are **async** and need an active DB session in scope. In a request that's set up
> for you; in scripts and tests, run them inside the framework's session context.

## Assign and check

```python
await user.assign_role("editor")
await user.give_permission_to("posts.publish")

await user.has_role("editor")              # -> bool
await user.has_any_role("editor", "admin")
await user.has_permission_to("posts.publish")
names = await user.get_role_names()
```

Other methods: `remove_role`, `sync_roles`, `has_all_roles`, `has_level`, `revoke_permission_to`,
`sync_permissions`, `get_all_permissions`, `get_direct_permissions`, `get_permissions_via_roles`.

Permissions resolve through roles automatically — `has_permission_to` is true when the user holds the
permission directly **or** via any assigned role. With `wildcard_enabled` (the default), a held
`posts.*` satisfies a check for `posts.edit`.

## Route middleware

The package ships three middleware classes. Register them yourself — the provider does not wire them:

```python
from arvel_permission import RoleMiddleware, PermissionMiddleware, RoleOrPermissionMiddleware

RoleMiddleware("admin")
PermissionMiddleware("posts.publish")
RoleOrPermissionMiddleware("admin|posts.publish")   # pipe = OR
```

A failed check raises `UnauthorizedException`, which the framework's default handler turns into a 401
(unauthenticated) or 403 (unauthorized) response.

## Gate integration

When `PermissionServiceProvider` boots and a `Gate` is bound, it registers a `before` hook so
`await gate.allows("posts.edit", user)` resolves through the user's permissions. If no `Gate` is
bound, this is skipped silently — no manual wiring needed.

## Configuration

`PermissionConfig` is a frozen model — there are **no environment variables**. Override defaults by
setting the provider's `config` before boot:

```python
from arvel_permission import PermissionConfig, PermissionServiceProvider


class AppPermissionProvider(PermissionServiceProvider):
    config = PermissionConfig(default_guard_name="api", wildcard_enabled=True)
```

Notable fields: `default_guard_name` (`web`), `cache_enabled` (`true`), `wildcard_enabled` (`true`),
`events_enabled` (`false`), `cache_ttl` (`86400`).

## Spatie ↔ arvel-permission

| Spatie (PHP) | arvel-permission (Python) |
|---|---|
| `assignRole` | `assign_role` |
| `removeRole` | `remove_role` |
| `syncRoles` | `sync_roles` |
| `hasRole` | `has_role` |
| `hasAnyRole` | `has_any_role` |
| `hasAllRoles` | `has_all_roles` |
| `givePermissionTo` | `give_permission_to` |
| `revokePermissionTo` | `revoke_permission_to` |
| `syncPermissions` | `sync_permissions` |
| `hasPermissionTo` | `has_permission_to` |
| `getAllPermissions` | `get_all_permissions` |
| `getRoleNames` | `get_role_names` |

## License

MIT — see [LICENSE](../../LICENSE).
