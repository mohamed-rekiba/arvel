# arvel-permission

<p>
<a href="https://pypi.org/project/arvel-permission/">
    <img src="https://img.shields.io/pypi/v/arvel-permission?color=%2334D058&label=pypi" alt="PyPI">
</a>
<img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License">
</p>

Roles and permissions for [Arvel](https://arvel.dev) — a Python port of
[spatie/laravel-permission](https://spatie.be/docs/laravel-permission/v7/introduction) v7.

> **Status**: Pre-alpha — `v0.3.0`.

---

**Documentation**: <a href="https://arvel.dev/permission" target="_blank">https://arvel.dev/permission</a>

---

## Install

```bash
uv add arvel-permission
# or: pip install arvel-permission
```

Register the provider in `bootstrap/providers.py`:

```python
from arvel_permission import PermissionServiceProvider

PROVIDERS = [
    # ...other providers...
    PermissionServiceProvider,
]
```

Run the migration (adds `roles`, `permissions`, `model_has_roles`, `model_has_permissions`,
`role_has_permissions`):

```bash
arvel migrate
```

## Quick start

Mix `HasRoles` and `HasPermissions` into any model:

```python
from arvel.database import Model, Timestamps, id_, string
from arvel_permission import HasRoles, HasPermissions


class User(Model, Timestamps, HasRoles, HasPermissions):
    __tablename__ = "users"

    id: int = id_()
    email: str = string(254, unique=True)
```

Manage roles and permissions:

```python
user = await User.find(user_id)

# assign_role / give_permission_to mutate in-memory; await save() flushes to the DB
user.assign_role("editor")
user.assign_role("writer")
user.give_permission_to("edit articles")
user.give_permission_to("delete articles")
await user.save()

# Check
assert user.has_role("editor")
assert user.has_any_role(["editor", "admin"])
assert user.has_permission_to("edit articles")
```

## Roles

```python
from arvel_permission.models import Role, Permission
from arvel.facades import DB

# Create a role with permissions
editor = Role(name="editor", guard_name="api")
await DB.session().add(editor)

publish = Permission(name="publish articles", guard_name="api")
await DB.session().add(publish)

editor.sync_permissions([publish])
await DB.session().commit()

# Assign to user
user.assign_role(editor)

# Get role names
print(user.get_role_names())          # ["editor"]
print(user.get_permission_names())    # ["publish articles"]
print(user.get_all_permissions())     # includes inherited permissions
```

## Route middleware

Protect routes by role or permission using the registered middleware:

```python
@Route.get("/admin", middleware=["role:admin"])
async def admin_panel() -> dict[str, str]:
    return {"panel": "admin"}

@Route.post("/articles", middleware=["permission:publish articles"])
async def publish_article() -> dict[str, str]:
    return {"published": True}

# Pipe-separated → OR semantics
@Route.get("/dashboard", middleware=["role:admin|manager"])
async def dashboard() -> dict[str, str]:
    return {"ok": True}
```

Middleware raises `UnauthorizedException` (401 when unauthenticated, 403 when unauthorized).
The framework's default exception handler converts it to the correct HTTP response.

## Gate integration

Wire permissions into Arvel's `Gate` so `gate.allows("edit articles", user)` works without
manually registering each ability:

```python
from arvel_permission.gate_integration import register_permissions_with_gate
from arvel.facades import Gate as ArvelGate

register_permissions_with_gate(ArvelGate, guard="api")

# Now these work
allowed = await ArvelGate.allows("edit articles", user)
```

## Events (opt-in)

Enable role/permission mutation events for audit logs or cache invalidation:

```python
from arvel_permission import PermissionConfig

config = PermissionConfig(events_enabled=True)
```

Subscribe to events:

```python
from arvel_permission.events import RoleAttachedEvent, PermissionGrantedEvent, on

@on(RoleAttachedEvent)
def audit_role(event: RoleAttachedEvent) -> None:
    print(f"Role '{event.role.name}' attached to {event.model}")

@on(PermissionGrantedEvent)
def audit_permission(event: PermissionGrantedEvent) -> None:
    print(f"Permission '{event.permission.name}' granted to {event.model}")
```

Events are in-process only — not dispatched through Arvel's async queue.

## Configuration

All knobs are a Pydantic model:

```python
from arvel_permission import PermissionConfig, PermissionServiceProvider

class MyPermissionProvider(PermissionServiceProvider):
    def register(self) -> None:
        self.config = PermissionConfig(
            default_guard_name="api",   # default: "web"
            cache_enabled=True,         # set False in tests
            wildcard_enabled=True,      # "posts.*" matches "posts.edit"
        )
```

## Spatie ↔ arvel-permission API

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
| `getPermissionNames` | `get_permission_names` |

## License

MIT — see [LICENSE](../../LICENSE).
