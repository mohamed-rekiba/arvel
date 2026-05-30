# Roles & Permissions

`arvel-permission` is Arvel's port of [Spatie Laravel Permission v7](https://spatie.be/docs/laravel-permission/v7/introduction). It gives any model in your app a Spatie-shaped roles-and-permissions API, scoped by guard, with `Gate` integration so that `Gate.allows("edit articles")` "just works" once a user has been granted the matching permission.

`arvel-permission` is a separate workspace package. Install it through the `permission` extra:

```bash
uv add "arvel[permission]"
```

## Migration

The package ships a publishable migration that creates five tables: `roles`, `permissions`, and the three pivots (`model_has_roles`, `model_has_permissions`, `role_has_permissions`).

```bash
arvel vendor:publish --tag=arvel-permission
arvel migrate
```

Both `roles` and `permissions` enforce `UNIQUE(name, guard_name)`, so the same role name can exist under multiple guards (a `web` admin and an `api` admin are distinct).

The two pivot tables (`model_has_roles`, `model_has_permissions`) use a **composite primary key** — `(role_id / permission_id, model_type, model_id)` — with no surrogate `id` column and no timestamps. This matches Spatie v7's default schema and enforces uniqueness at the database level. The async `MorphToMany` accessor that drives these pivots dedups before inserting, so assigning the same role twice is a no-op rather than an `IntegrityError`.

## Models

`Role` and `Permission` are regular Arvel models. You can query them like any other model:

```python
from arvel_permission import Permission, Role


role = await Role.where(Role.name == "editor").first()
perms = await Permission.where(Permission.guard_name == "api").all()
```

`Permission` also exposes a `roles` relation (a `BelongsToMany` accessor over `role_has_permissions`), so you can navigate the assignment graph in both directions:

```python
perm = await Permission.find_by_name("edit articles", session=db)
for role in await perm.roles.all():
    print(role.name)  # every role that carries this permission
```

### Async lookup helpers

`Role` and `Permission` both expose convenience class methods for the most common DB lookups:

```python
# Raises RoleDoesNotExist if not found
role = await Role.find_by_name("editor", session=db)

# Never raises — creates and persists if absent
role = await Role.find_or_create("editor", session=db)

# Look up by primary key
role = await Role.find_by_id(42, session=db)
```

The same set — `find_by_name`, `find_by_id`, `find_or_create` — is available on `Permission`.

### Typed exceptions

When a lookup by name fails, the package raises a typed exception rather than returning `None`:

```python
from arvel_permission import RoleDoesNotExist, PermissionDoesNotExist


try:
    role = await Role.find_by_name("nonexistent", session=db)
except RoleDoesNotExist:
    ...
```

The middleware and authorization layer also raises `UnauthorizedException`:

```python
from arvel_permission import UnauthorizedException


# status_code is 401 (no user) or 403 (user lacks access)
try:
    ...
except UnauthorizedException as exc:
    return JSONResponse({"error": "Forbidden"}, status_code=exc.status_code)
```

Register a global handler in your app's exception handler so middleware failures return a clean HTTP response:

```python
from starlette.requests import Request
from starlette.responses import JSONResponse

from arvel_permission import UnauthorizedException


async def permission_exception_handler(
    request: Request,
    exc: UnauthorizedException,
) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": "FORBIDDEN", "message": str(exc)}},
        status_code=exc.status_code,
    )


app.add_exception_handler(UnauthorizedException, permission_exception_handler)
```

## Mixins

Add `HasRoles` and `HasPermissions` to any user model. The mixins are **async-first**: every grant, revoke, and check hits the active session directly, so there's no in-memory collection to flush.

The host declares `roles` and `permissions` as `MorphToMany` accessors over the polymorphic pivots. The accessor writes the `model_type` discriminator and string-casts the owner PK into the `VARCHAR(36)` `model_id` column on every INSERT — so API-assigned grants always persist, with no `cast()` calls, no `# type: ignore`, and no `model_type`-NULL bug class:

```python
from typing import ClassVar

from arvel.database import Model, Timestamps
from arvel.database.columns import id_, string
from arvel.database.orm import Mapped, MorphToMany
from arvel_permission import HasPermissions, HasRoles, Permission, Role
from arvel_permission.models import model_has_permissions, model_has_roles


class User(Model, Timestamps, HasRoles, HasPermissions):
    __tablename__ = "users"

    id: Mapped[int] = id_()
    name: Mapped[str] = string(255)
    default_guard_name = "web"

    roles: ClassVar[MorphToMany[Role]] = MorphToMany(
        Role, table=model_has_roles, name="model", related_key="role_id"
    )
    permissions: ClassVar[MorphToMany[Permission]] = MorphToMany(
        Permission, table=model_has_permissions, name="model", related_key="permission_id"
    )
```

`name="model"` names the pivot discriminator pair (`model_type` / `model_id`); `MorphToMany` derives the `model_type` value from the host's short class name (`"User"`) automatically.

!!! note "Async relations don't load via `with_()`"
    `QueryBuilder.with_()` only eager-loads SQLAlchemy `relationship()` properties. `MorphToMany` is a custom async descriptor, so load it on demand with `await user.roles.all()` rather than `User.with_("roles")`. See [Arvent relationships](arvent-relationships.md#morphtomany).

### Roles

```python
await user.assign_role("editor")
await user.assign_role("editor", "moderator")  # multi-arg, deduped
await user.has_role("editor")                   # True
await user.has_any_role("editor", "admin")      # True
await user.has_all_roles("editor", "moderator") # True
await user.get_role_names()                     # ["editor", "moderator"]

await user.remove_role("moderator")
await user.sync_roles(["editor", "author"])               # replaces the set wholesale
await user.sync_roles(["editor", "author"], detach=False) # appends, keeps existing roles
```

Each call persists immediately through the accessor — there's no separate `save()` step for role and permission grants. The roles themselves are find-or-created by name and guard, so `assign_role("editor")` works even if the `editor` row doesn't exist yet.

All mixin methods accept plain strings **or** `StrEnum` values, so you can use an enum to define your app's role set without losing type safety:

```python
import enum


class AppRole(enum.StrEnum):
    EDITOR = "editor"
    ADMIN = "admin"


await user.assign_role(AppRole.EDITOR)
await user.has_role(AppRole.ADMIN)  # False
```

### Permissions

```python
await user.give_permission_to("edit articles")
await user.has_permission_to("edit articles")   # True
await user.has_any_permission("edit articles", "delete articles")
await user.get_permission_names()               # ["edit articles", ...]

await user.revoke_permission_to("edit articles")
await user.sync_permissions(["edit articles", "publish articles"])
```

`has_permission_to` checks **direct** permissions plus permissions **inherited via roles** — exactly the Spatie semantics.

#### Direct vs inherited

When you need to distinguish where a permission came from:

```python
await user.get_direct_permissions()      # only directly granted
await user.get_permissions_via_roles()   # only inherited through roles
await user.get_all_permissions()         # union of both, de-duped
```

#### Wildcard permissions

`has_permission_to` evaluates wildcard patterns held by the user. Patterns follow the Apache Shiro model: use `*` for any segment and comma-separate alternatives within a segment:

```python
await user.give_permission_to("edit.*")
await user.has_permission_to("edit.articles")  # True
await user.has_permission_to("edit.comments") # True
await user.has_permission_to("delete.posts")  # False

# Match any ability
await user.give_permission_to("*")
await user.has_permission_to("anything.at.all")  # True

# Comma-separated OR within a segment
await user.give_permission_to("posts,users.create,update")
await user.has_permission_to("posts.create")  # True
await user.has_permission_to("users.update")  # True
await user.has_permission_to("users.delete")  # False

# Star on one segment, OR list on another
await user.give_permission_to("*.create,update")
await user.has_permission_to("articles.create")  # True
await user.has_permission_to("comments.update")  # True
await user.has_permission_to("posts.delete")     # False
```

To disable wildcard matching for a specific model class, set the class attribute:

```python
class RestrictedUser(HasPermissions):
    wildcard_permission = False  # exact match only
```

To change the default for **all** models at once, set `wildcard_enabled` on `PermissionConfig` before boot. See [Configuration](#configuration).

### Permissions on roles

`Role` also mixes in `HasPermissions`, so you can assign permissions directly to a role:

```python
editor_role = await Role.find_or_create("editor", session=db, guard="web")
await editor_role.give_permission_to("edit articles", "publish articles")
await editor_role.has_permission_to("edit articles")  # True

await editor_role.revoke_permission_to("publish articles")
await editor_role.sync_permissions(["edit articles"])
```

Any user assigned the `editor` role will inherit these permissions via `has_permission_to`.

### Query scopes

`HasRoles` and `HasPermissions` each provide async classmethods for bulk DB queries — useful in admin panels, reporting, and seeding:

```python
from sqlalchemy.ext.asyncio import AsyncSession


# All users with the "editor" role
editors = await User.query_with_role("editor", session=db)

# All users without the "admin" role
non_admins = await User.query_without_role("admin", session=db)

# All users with the "publish articles" permission (direct grants only)
publishers = await User.query_with_permission("publish articles", session=db)

# All users lacking the "delete posts" permission
others = await User.query_without_permission("delete posts", session=db)
```

All four accept an optional `guard=` keyword (default `"web"`):

```python
api_admins = await User.query_with_role("admin", session=db, guard="api")
```

These queries check **direct assignments only** (the pivot tables). Permissions inherited through roles are not included in `query_with_permission` / `query_without_permission`.

## Guard scoping

Every check accepts an optional `guard=` keyword. Asking under the wrong guard raises `GuardMismatchError`:

```python
from arvel_permission import GuardMismatchError


api_admin = await Role.find_or_create("admin", session=db, guard="api")
await user.assign_role(api_admin)

await user.has_role("admin", guard="api")    # True
try:
    await user.has_role(api_admin, guard="web")
except GuardMismatchError:
    pass  # Item belongs to guard 'api' but caller asked about 'web'.
```

If you don't pass `guard=`, the model's `default_guard_name` is used (defaults to `"web"`).

## Route middleware

`arvel-permission` ships three ready-to-use route middleware classes. Register them in your provider's `boot()` method:

```python
from arvel_permission import PermissionServiceProvider
from arvel_permission.middleware import (
    PermissionMiddleware,
    RoleMiddleware,
    RoleOrPermissionMiddleware,
)


class AppServiceProvider(PermissionServiceProvider):
    def boot(self) -> None:
        super().boot()
        self.router.middleware("role", RoleMiddleware)
        self.router.middleware("permission", PermissionMiddleware)
        self.router.middleware("role_or_permission", RoleOrPermissionMiddleware)
```

Then protect routes:

```python
@app.get("/admin/dashboard", middleware=["role:admin"])
async def admin_dashboard(request): ...

@app.post("/articles", middleware=["permission:publish articles"])
async def publish_article(request): ...

@app.get("/content", middleware=["role_or_permission:editor"])
async def content_page(request): ...
```

### Pipe-separated OR

Separate values with `|` to express OR semantics — the request passes if the user satisfies **any** of the listed values:

```python
@app.get("/dashboard", middleware=["role:admin|manager"])
async def dashboard(request): ...

@app.post("/posts", middleware=["permission:publish|edit"])
async def posts(request): ...
```

### Guard forwarding

Pass the guard name as a constructor keyword when you need non-default guard scoping:

```python
from arvel_permission.middleware import RoleMiddleware


class AppServiceProvider(PermissionServiceProvider):
    def boot(self) -> None:
        super().boot()
        # This instance checks roles against the "api" guard.
        self.router.middleware("api_role", RoleMiddleware("admin", guard="api"))
```

### Exception handling

All three middleware classes raise `UnauthorizedException` on failure — `status_code=401` when there is no authenticated user, `status_code=403` when the user exists but lacks access. The exception propagates up to your app's exception handler.

Register a handler so API clients receive a structured JSON response:

```python
from starlette.requests import Request
from starlette.responses import JSONResponse

from arvel_permission import UnauthorizedException


async def handle_unauthorized(request: Request, exc: UnauthorizedException) -> JSONResponse:
    return JSONResponse({"error": "Forbidden"}, status_code=exc.status_code)


app.add_exception_handler(UnauthorizedException, handle_unauthorized)
```

!!! warning "Breaking change from pre-0.51 middleware"
    Prior to version 0.51 the middleware returned a Starlette `Response` directly. It now raises `UnauthorizedException` instead. Any code that checked middleware return values must be updated to handle the exception.

## Gate integration

`PermissionServiceProvider` hooks `register_permissions_with_gate(gate)` so any ability you check through `Gate` resolves to `user.has_permission_to(ability)` automatically.

Register the provider in `bootstrap/providers.py`:

```python
from arvel_permission import PermissionServiceProvider


PROVIDERS = [
    # ...your other providers...
    PermissionServiceProvider,
]
```

Now this works end-to-end:

```python
from arvel.facades import Gate


await user.give_permission_to("publish articles")

await Gate.allows("publish articles")  # True
```

You can still combine ability-style gates and policy-style permissions — `PermissionServiceProvider` adds a fallback resolver, it doesn't replace gates you've defined explicitly with `Gate.define(...)`.

## Configuration

`PermissionConfig` is a frozen Pydantic model that controls package-wide defaults. Override it in your provider's `register()` before boot:

```python
from arvel_permission import PermissionServiceProvider
from arvel_permission.config import PermissionConfig


class AppServiceProvider(PermissionServiceProvider):
    def register(self) -> None:
        self.config = PermissionConfig(
            default_guard_name="api",
            cache_enabled=False,    # disable for tests
            cache_store="redis",    # optional; pass the matching CacheStore to the registrar
            cache_ttl=86400,
            wildcard_enabled=True,  # default; set False to require exact matches globally
            events_enabled=True,    # opt-in to role/permission mutation events
        )
```

| Key | Default | Description |
|---|---|---|
| `default_guard_name` | `"web"` | Guard applied when none is supplied |
| `roles_table` | `"roles"` | DB table name for roles |
| `permissions_table` | `"permissions"` | DB table name for permissions |
| `model_has_roles_table` | `"model_has_roles"` | Pivot table |
| `model_has_permissions_table` | `"model_has_permissions"` | Pivot table |
| `role_has_permissions_table` | `"role_has_permissions"` | Pivot table |
| `cache_enabled` | `True` | `False` hits the DB on every lookup |
| `cache_store` | `None` | Optional persistent store name; pass the matching `CacheStore` to `PermissionRegistrar` |
| `cache_ttl` | `86400` | TTL in seconds for persistent role/permission cache entries |
| `cache_prefix` | `"arvel.permission"` | App-scoped cache key prefix |
| `wildcard_enabled` | `True` | Controls whether `*` and `,` patterns are evaluated |
| `events_enabled` | `False` | Opt-in to the role/permission mutation event system |
| `role_model` | `Role` | Custom `Role` subclass used by the registrar and mixins |
| `permission_model` | `Permission` | Custom `Permission` subclass used by the registrar and mixins |

## Events

When `events_enabled=True` is set on `PermissionConfig`, every role and permission mutation fires a typed event. Listeners are in-process only — not routed through Arvel's async job queue.

```python
from arvel_permission import events
from arvel_permission.events import (
    PermissionAttachedEvent,
    PermissionDetachedEvent,
    RoleAttachedEvent,
    RoleDetachedEvent,
)


@events.on(RoleAttachedEvent)
def audit_role_attach(evt: RoleAttachedEvent) -> None:
    print(f"role '{evt.role.name}' attached to {evt.model!r}")


@events.on(RoleDetachedEvent)
def audit_role_detach(evt: RoleDetachedEvent) -> None:
    print(f"role '{evt.role.name}' detached from {evt.model!r}")


@events.on(PermissionAttachedEvent)
def invalidate_perm_cache(evt: PermissionAttachedEvent) -> None:
    cache.delete(f"user:{id(evt.model)}:perms")
```

Listeners can also be registered without the decorator:

```python
events.on(RoleAttachedEvent, audit_role_attach)
```

To fire a custom event manually:

```python
events.fire(RoleAttachedEvent(model=user, role=role))
```

| Event | When |
|---|---|
| `RoleAttachedEvent` | After `assign_role()` |
| `RoleDetachedEvent` | After `remove_role()` or `sync_roles()` detach |
| `PermissionAttachedEvent` | After `give_permission_to()` |
| `PermissionDetachedEvent` | After `revoke_permission_to()` or `sync_permissions()` detach |

All events are frozen dataclasses with two fields: `model` (the host object) and `role`/`permission` (the affected `Role` or `Permission` instance).

## PermissionRegistrar

For app code that needs to find or create roles and permissions outside of a model context (seeders, REPL exploration, admin panels), use `PermissionRegistrar`:

```python
from arvel_permission import PermissionRegistrar


registrar = PermissionRegistrar()                       # in-memory
registrar.register_role("editor")
registrar.register_permission("publish articles")

# DB-backed: pass an AsyncSession
registrar = PermissionRegistrar(session)
await registrar.a_register_role("editor")
await registrar.a_register_permission("publish articles")

registrar.refresh_cache()                               # invalidate per-instance cache
```

The default cache is per-instance and in-memory. To share role and permission lookups across registrar instances, pass a configured Arvel cache store:

```python
from arvel.cache.stores.redis_ import RedisStore
from arvel_permission.config import PermissionConfig
from arvel_permission import PermissionRegistrar


config = PermissionConfig(
    cache_store="redis",
    cache_ttl=86400,
    cache_prefix="my-app.permission",
)
store = RedisStore(url="redis://localhost:6379/0", prefix="my-app")
registrar = PermissionRegistrar(session, config=config, cache_store=store)
await registrar.a_register_role("editor")
await registrar.a_refresh_cache()
```

To disable caching entirely:

```python
from arvel_permission.config import PermissionConfig


registrar = PermissionRegistrar(config=PermissionConfig(cache_enabled=False))
```

## Extending the models

Use `role_model` and `permission_model` when your app needs custom columns or helpers on the RBAC models. The custom classes must extend the built-in `Role` and `Permission` classes.

```python
from arvel_permission.config import PermissionConfig
from arvel_permission import PermissionRegistrar
from arvel_permission.models import Permission, Role


class AppRole(Role):
    pass


class AppPermission(Permission):
    pass


config = PermissionConfig(role_model=AppRole, permission_model=AppPermission)
registrar = PermissionRegistrar(config=config)
role = registrar.register_role("editor")
assert isinstance(role, AppRole)
```

## See also

- [Authorization](authorization.md) — Gates and Policies (the layer this package wires into)
- [Authentication](authentication.md) — guards and the user model
- [Middleware](middleware.md) — full middleware reference
