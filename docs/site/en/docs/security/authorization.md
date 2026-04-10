# Authorization

Authentication proves identity; **authorization** decides what that identity may do. Arvel ships **policy classes**, a **`PolicyRegistry`**, and a **`Gate`** helper so you can express rules once and reuse them from HTTP handlers, jobs, and domain services—Laravel developers will recognize the shape immediately.

At **v0.1.0**, **`Policy`** uses a **method-per-action** pattern (`view`, `update`, `delete`, …) with a **deny-by-default** mindset. **`RoleBasedPolicy`** reads roles from **JWT/OIDC claims** via the claims mapper when you need provider-specific group layouts.

## Policies

Subclass **`Policy`** and implement async methods that take a **user context** and optionally a **resource**. Name methods after your actions so call sites read like sentences.

```python
from arvel.auth.policy import Policy


class PostPolicy(Policy):
    async def update(self, user: object, post: object) -> bool:
        return getattr(post, "author_id", None) == getattr(user, "id", None)

    async def delete(self, user: object, post: object) -> bool:
        return await self.update(user, post) or getattr(user, "is_admin", False)
```

Register policies on **`PolicyRegistry`** with **`register(Model, PolicySubclass)`** so the gate can resolve the right policy for a model type.

## Gate

**`Gate`** is the façade you inject into request scope. Given a user, an action name, and optionally an instance or type, it finds the policy, runs **`before`** hooks if present, dispatches to the action method, and returns **allow/deny**. It logs structured decisions—handy when you debug “why was this 403?”

```python
from arvel.auth.policy import Gate, PolicyRegistry


registry = PolicyRegistry()
# registry.register(Post, PostPolicy)

gate = Gate(registry)


async def update_post(gate: Gate, user: object, post: object) -> None:
    if not await gate.allows(user, "update", post):
        raise PermissionError("Cannot update post")
```

If **`Gate.allows`** is called without enough context, it **denies** and warns—better a failed action than an accidental permit.

## Roles from OIDC

When users arrive with rich **`realm_access.roles`**, **`groups`**, or custom arrays, configure the **claims mapper** so **`RoleBasedPolicy`** and friends see a consistent role list. Keep vendor-specific parsing out of individual policies when you can.

## Layering

Use policies for **domain rules**, middleware for **coarse guards** (authenticated routes), and **never** mix authorization checks only in templates—always enforce on the server.

That keeps Arvel apps **predictable**: one gate, one registry, explicit denials, and tests that can instantiate policies without HTTP.
