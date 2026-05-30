# Authorization

After [Authentication](authentication.md) tells you *who* the user is, authorization tells you *what they can do*. Arvel ships two complementary patterns:

- **Gates** — simple, function-style ability checks for one-off rules.
- **Policies** — class-based permission rules attached to a model.

Both fail closed: if no rule says "yes", the answer is "no". See ADR-032 for the rationale.

`Gate` is a **DI singleton** — `container.make(Gate)` always returns the same instance, so gates you define in one provider are visible across the entire application.

## Gates

Define a gate in a service provider:

```python
from arvel.facades import Gate


class AuthServiceProvider(ServiceProvider):
    async def boot(self) -> None:
        Gate.define("manage-billing", lambda user: user.is_owner)
        Gate.define("edit-post", lambda user, post: user.id == post.author_id)
```

Check a gate:

```python
@Route.delete("/billing/account")
async def delete_account() -> dict:
    if not await Gate.allows("manage-billing"):
        raise AuthorizationException()
    ...
```

`Gate.allows(...)` returns a `bool`. `Gate.authorize(...)` raises `AuthorizationException` on denial.

For ergonomics, use it as middleware:

```python
@Route.delete("/billing/account", middleware=[Authorize("manage-billing")])
async def delete_account() -> dict: ...
```

## Policies

For per-model permissions, write a policy class:

```python
from arvel.auth import Policy


class PostPolicy(Policy):
    def view(self, user, post: Post) -> bool:
        return post.published or post.author_id == user.id

    def update(self, user, post: Post) -> bool:
        return post.author_id == user.id

    def delete(self, user, post: Post) -> bool:
        return post.author_id == user.id or user.is_admin
```

Register it:

```python
class AuthServiceProvider(ServiceProvider):
    async def boot(self) -> None:
        Gate.policy(Post, PostPolicy)
```

Use it:

```python
@Route.put("/posts/{post_id}")
async def update(post_id: int, form: UpdatePost) -> dict:
    post = await Post.find_or_fail(post_id)
    await Gate.authorize("update", post)
    ...
```

Or as middleware:

```python
@Route.delete("/posts/{post_id}", middleware=[Authorize("delete", Post)])
async def destroy(post_id: int) -> dict:
    ...
```

The middleware resolves the model instance via the `{post_id}` parameter using your routing convention.

## Sync and async policies

Policy methods can be either sync or async — use whichever fits the rule:

```python
class PostPolicy(Policy):
    def view(self, user, post: Post) -> bool:
        # Sync: no I/O needed
        return post.published or post.author_id == user.id

    async def update(self, user, post: Post) -> bool:
        # Async: needs a database query
        return await is_collaborator(user, post)
```

Gate callables follow the same rule — sync lambdas and async functions both work:

```python
Gate.define("manage-billing", lambda user: user.is_owner)   # sync

Gate.define(
    "view-organization",
    lambda user, org_id: org_membership_exists(user.id, org_id),  # async coroutine
)
```

## Inspecting denial reasons

For richer error responses, return a `Response` instead of `False`:

```python
Gate.define(
    "manage-billing",
    lambda user: True if user.is_owner else Gate.deny("Only owners can manage billing."),
)
```

The denial message lands in the `AuthorizationException` and propagates to the 403 response body.

## Bypass for super-admins

```python
Gate.before(lambda user, ability: True if user.is_super_admin else None)
```

`before` callbacks run first; returning a non-None value short-circuits the gate.

## Policy resolution

When `Gate.authorize("update", post)` runs, Arvel:

1. Looks at `post.__class__` (`Post`).
2. Finds the registered policy for `Post` (`PostPolicy`).
3. Calls `PostPolicy().update(user, post)`.
4. Returns the result, raising on `False` if you called `authorize`.

If no policy is registered for a model, all ability checks return `False`.

## Inside FormRequests

A `FormRequest.authorize()` method runs after validation. It's the natural place to call gates and policies:

```python
class UpdatePost(FormRequest[UpdatePostPayload]):
    async def authorize(self, request) -> bool:
        payload = self.validated()
        post = await Post.find(payload.post_id)
        return post is not None and await Gate.allows("update", post)
```

## Testing

```python
async def test_user_cannot_edit_others_post(client) -> None:
    alice = await UserFactory().create()
    bob = await UserFactory().create()
    post = await PostFactory().for_user(alice).create()
    Auth.login(bob)

    response = await client.put(f"/posts/{post.id}", json={"title": "..."})
    assert response.status_code == 403
```

## Where to next?

- [Authentication](authentication.md) — resolving the user in the first place.
- [Requests](requests.md) — wiring `authorize()` into form requests.
- [Middleware](middleware.md) — the `Authorize` middleware in the pipeline.
