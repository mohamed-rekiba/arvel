# Authorization: Roles & Permissions

Authentication told you *who* the user is. Authorization answers the next question: *what are they
allowed to do?* arvel gives you two complementary tools, and most apps use both:

- **Roles & permissions** — coarse, role-based access. "Editors can publish posts." Great for
  app-wide capabilities a user either has or doesn't.
- **Gates & policies** — fine-grained, per-object rules. "You can edit *this* post because you wrote
  it." Great when the answer depends on the specific record.

Whatever the source — assigned by an admin or [derived from an SSO group](idp-roles.md) — there is
exactly one authorization vocabulary: **`Role`** and **`Permission`**. This page covers both tools.

## Roles & permissions

Make your user model carry roles by mixing in `HasRoles`:

```python
from arvel import Model
from arvel.auth import Authenticatable, HasRoles

class User(Model, Authenticatable, HasRoles):
    __fields__ = {"email": str, "name": str}
    __fillable__ = ["email", "name"]
```

Define permissions, group them into roles, and assign roles to users:

```python
from arvel.auth import Role, Permission

await Permission.create(name="posts.publish", guard_name="web")
editor = await Role.create(name="editor", guard_name="web")
await editor.give_permission_to("posts.publish")     # role → permission

await user.assign_role("editor")                     # user → role
```

Then ask:

```python
await user.has_role("editor")                # True
await user.has_permission_to("posts.publish")  # True — inherited via the editor role
[r.name for r in await user.roles()]         # ["editor"]
```

You can also grant a permission to a user **directly**, without a role:

```python
await user.give_permission_to("reports.export")
await user.has_permission_to("reports.export")   # True
```

A user's effective permissions are the union of their direct grants and everything their roles
confer.

### Wildcards

Permission names are plain strings, so adopt a `resource.action` convention (`posts.edit`,
`posts.publish`) — it unlocks two wildcards:

```python
# A role/grant holding "posts.*" satisfies any posts.* check:
await user.has_permission_to("posts.edit")     # True if the user has "posts.*"

# "*" is the super-admin grant — it satisfies EVERY permission check:
await user.has_permission_to("anything.at.all") # True if the user has "*"
```

!!! warning "`*` is total power"
    A grant of `*` passes every permission check there is. Reserve it for a genuine super-admin role,
    and be especially careful which roles can carry it when roles can come from
    [an identity provider](idp-roles.md).

## Gates: ability checks

A **gate** is a named rule — a callback that receives the user (and any arguments) and returns whether
they may do something. Define gates on the `Gate`, then ask via `user.can(...)`:

```python
from arvel.auth import Gate

gate = Gate()
gate.define("settings.manage", lambda user: user.has_role("admin"))

await user.can("settings.manage")          # True / False
```

For per-object decisions, pass the object — the gate callback receives it:

```python
gate.define("post.update", lambda user, post: post.author_id == user.id)

await user.can("post.update", post)        # may *this* user edit *this* post?
```

To enforce instead of ask, `authorize` raises `AuthorizationError` when denied. The exception carries
the deny **message** and **status** straight through to the HTTP response (it renders as that status,
not a generic 500):

```python
await gate.authorize("post.update", post, user=user)   # raises AuthorizationError if not allowed
```

A callback can return a bool, or a `GateResponse` for a custom message/status — and that message +
status survive to the response (and to `gate.inspect(...)`, which returns the full `GateResponse`):

```python
from arvel.auth import GateResponse

def can_publish(user, post):
    if post.is_locked:
        return GateResponse.deny("This post is locked.", code=423)   # → HTTP 423 + this message
    return GateResponse.allow()

gate.define("post.publish", can_publish)

resp = await gate.inspect("post.publish", post, user=user)   # the real GateResponse
resp.allowed, resp.message, resp.code
```

Use `GateResponse.deny_as_not_found()` to deny **as a 404** — hiding a resource's existence from a
user who may not even know it's there:

```python
def view(self, user, post):
    return GateResponse.allow() if post.is_public else GateResponse.deny_as_not_found()
```

## Policies: gates grouped by model

When a model has several abilities, group them in a **policy** class — one method per ability — and
register it:

```python
class PostPolicy:
    async def update(self, user, post):
        return post.author_id == user.id

    async def delete(self, user, post):
        return post.author_id == user.id or await user.has_role("admin")

gate.policy(Post, PostPolicy())

await user.can("update", post)     # routed to PostPolicy.update
```

The ability name is the **method name, exactly** — `can("update", …)` calls `update`, and there's no
snake↔camel conversion, so `can("view_any", …)` looks for a `view_any` method, not `viewAny`. Pick one
spelling and use it on both sides. To mirror the standard resource policies, name your methods
(and abilities) in camelCase — `viewAny`, `view`, `create`, `update`, `delete`, `restore`,
`forceDelete` — and call them with the same string: `can("viewAny", Post)`.

### Policy auto-discovery

You don't have to call `gate.policy(Model, Policy)` for every model. `Gate.resolve_policy(model)`
checks three tiers, in order:

1. An **explicit** `gate.policy(Model, Policy)` registration — wins over everything else.
2. A `__policy__` classvar on the model itself — typed, preferred:

   ```python
   class Post(Model):
       __policy__ = PostPolicy
   ```

3. A **provider-registered convention map** — the closest arvel gets to an automatic
   `Model` → `ModelPolicy` guess. There's no filesystem/import magic inferring a policy from a class
   name: your app's `AuthServiceProvider` scans its own `policies/` package and hands the resulting
   map to `register_policies`:

   ```python
   gate.register_policies({Post: PostPolicy, Comment: CommentPolicy})
   ```

`user.can(...)`, `gate.allows(...)`, and every other check already call `resolve_policy` under the
hood — there's nothing else to wire up once a policy is registered by any of the three routes. An
unregistered model with no matching ability falls through to `Gate.define`/deny, same as always.

### Guests (unauthenticated checks)

A gate can be asked about a guest — `user=None` — e.g. a public-content check run before login. Two
outcomes, decided by the callback's **first parameter's type hint**:

```python
gate.define("view", lambda user: True)              # untyped → called with None (permissive)
gate.define("view", lambda user: user.is_admin)      # untyped → called with None too (may raise!)

def view(user: User) -> bool:                        # non-Optional → guest auto-denied,
    return user.is_admin                             # never called with None (no AttributeError)

def view(user: User | None) -> bool:                 # Optional/nullable → called with None;
    return user is not None and user.is_admin         # the policy opted into guest evaluation
```

An **untyped** parameter (the common case — plain lambdas) is treated as nullable for backward
compatibility; only an *explicit*, non-`Optional` type hint (`User`, not `User | None`) triggers the
auto-deny. `before` hooks still run first regardless (a `before` returning non-`None` short-circuits
before this check ever happens) — this only guards the ability/policy-method call itself. The
annotation inspection is cached per callback, so it costs nothing beyond the first check.

### Super-admin override with `before`

A `before` callback runs ahead of every check — return `True` to grant everything (the classic
super-admin shortcut), or `None` to fall through to the normal rule:

```python
gate.before(lambda user, ability: True if user.has_role("super-admin") else None)
```

A **policy** can carry its own `before` method too — it runs ahead of that policy's ability methods
(scoped super-admin / model-wide rules), returning `True`/`False` to decide, or `None` to fall
through to the per-ability method:

```python
class PostPolicy:
    def before(self, user, ability):
        return True if user.is_admin else None   # admins skip the per-ability checks below

    async def update(self, user, post):
        return post.author_id == user.id
```

## Impersonation ("login as")

Support and debugging sometimes need an admin to act *as* another user, then return to themselves.
`arvel.auth.impersonation` does this through the session — gated by an ability so only the right people
can start, and **reversible** so you always get back to the real admin:

```python
from arvel.auth.impersonation import impersonate, stop_impersonating, is_impersonating

# who may impersonate — defined like any other ability (fail closed if undefined)
gate.define("impersonate", lambda user, target: user.has_role("admin"))

async def start(request):
    target = await User.find(request.query("user_id"))
    if await impersonate(request, target):     # authorizes, switches identity, rotates the session
        return redirect("/")
    return "Not allowed", 403

async def leave(request):
    await stop_impersonating(request)          # back to the real admin
    return redirect("/admin")
```

`impersonate` stashes the real user's id (`_impersonator_id`) and points the active user
(`_user_id`, the key your `user_resolver` reads) at the target, **regenerating the session** on the
switch. It's fail-closed: a guest, an unauthorized user, impersonating yourself, or trying to nest a
second impersonation all return `False` and change nothing. Show a banner while it's active:

```python
if is_impersonating(request):
    banner = f"Impersonating — acting as {request.user().name}. [Leave](/leave)"
```

!!! warning "Stopping always returns to the *real* user"
    `stop_impersonating` restores the stashed impersonator and regenerates the session again. Because
    nesting is refused, there's exactly one identity to return to — impersonation can never escalate.

Every start, stop, and **denied** attempt emits a structured audit event on the `security` logging
channel (`auth.impersonation.started` / `.stopped` / `.denied`, with the impersonator and target
ids) — so "who acted as whom" is always recoverable. Route the `security` channel to durable storage
in production; impersonation is a privileged action and accountability is required, not optional.

## Common mistakes & gotchas

- **Ad-hoc permission strings.** They're just strings — without a convention you'll end up with
  `edit-posts`, `posts.edit`, and `editPost` all meaning the same thing. Pick `resource.action` and
  stick to it (it's also what makes `posts.*` work).
- **Handing out `*`.** It's total. Don't attach it to anything an IdP claim could map to without
  vetting (see [Mapping IdP Groups to Roles](idp-roles.md)).
- **Forgetting gates receive the user.** `user.can(ability, *args)` calls the gate with that user;
  define callbacks as `(user, *args)`.
- **Roles vs direct permissions.** Roles are for shared capability sets; a direct
  `give_permission_to` is for one-off grants. Both feed the same `has_permission_to` result.
- **Missing pivot tables.** RBAC uses `model_has_roles` / `model_has_permissions` /
  `role_has_permissions` — create them in a migration.

## How it works

`HasRoles` resolves a user's effective permissions as the union of **direct** grants and permissions
**via assigned roles**, read through the pivot tables and memoized per instance (call
`flush_permission_cache()` after granting/revoking). The match is wildcard-aware: an exact name, the
super-admin `*`, or a `prefix.*` that covers `prefix` and anything beneath it. The `Gate` resolves a
check in order: a `before` callback (short-circuits if it returns non-`None`) → a registered policy
method for the model (`resolve_policy`: explicit registration → `__policy__` classvar → provider
registry) → a named ability callback; `authorize` turns a denial into an `AuthorizationError`. A
guest (`user=None`) is only ever handed to a callback whose first parameter's type hint admits
`None` — otherwise the Gate denies without calling it.

## See also

- [Mapping IdP Groups to Roles](idp-roles.md) — roles that come from an identity provider.
- [Authentication](authentication.md) — establishing the user these checks run against.
- [Identities & Account Linking](identities.md) — the identity half of the same user.
