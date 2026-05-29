# API Tokens

Arvel ships opaque token authentication as part of the core [Authentication](authentication.md) layer — there's no separate package to install.

## Issuing tokens

```python
from arvel.facades import Auth

token = await Auth.guard("api").issue_token(
    subject=str(user.id),
    name="mobile-app",
    abilities=["read", "write"],
    expires_in=timedelta(days=30),
)
```

The token is a stable, opaque, URL-safe string. The plaintext is shown **once** at creation time; the database stores a SHA-256 hash.

## Authenticating requests

Apply the `Auth` middleware (with the `api` guard) to routes:

```python
@Route.get("/api/me", middleware=[Auth.guard("api")])
async def me(user: Annotated[User, Auth.user_dep()]) -> dict:
    return {"id": user.id, "name": user.name}
```

The client sends `Authorization: Bearer <token>`.

## Revoking tokens

```python
await user.tokens().where(name="mobile-app").delete()
```

## Token abilities (scopes)

```python
@Route.delete("/api/posts/{post_id}", middleware=[Auth.guard("api").with_abilities(["write"])])
async def delete_post(post_id: int): ...
```

Requests with a token that lacks the `write` ability get a `403`.

## SPA authentication

For first-party SPAs, prefer [session-based auth](authentication.md) with CSRF — it's simpler and avoids token storage on the client. Reserve tokens for mobile apps and third-party API consumers.

## See also

- [Authentication](authentication.md) — the full auth layer.
- [Authorization](authorization.md) — gating routes by abilities.
