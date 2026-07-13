# API Tokens

Sessions are great for browsers, but a CLI, a mobile app, or another service can't "log in with a
form." They need a credential they can put in a header on every request: a **bearer token**. arvel's
API tokens are high-entropy secrets you issue to a user; the client sends one as
`Authorization: Bearer <token>` and the token guard tells you which user it belongs to.

The important property: arvel stores **only a hash** of each token. The plaintext is shown to the user
exactly once, at creation — so even a full database leak hands an attacker nothing usable. This page
covers issuing tokens, authenticating with them, and the security model.

## Issuing a token

`create_token` mints a token for a user and returns the **plaintext once** alongside the stored
record. Show that plaintext to the user now — you can never retrieve it again:

```python
from arvel.auth.tokens import create_token

plaintext, token = await create_token(user, name="ci-deploy")
# → plaintext: "9f3a…" (64 hex chars) — display ONCE, then it's gone
# → token: the ApiToken row (only the hash is stored)

return {"token": plaintext}        # the only time the caller will ever see it
```

By default a token can do anything (`abilities=["*"]`) and never expires. Scope and time-box it:

```python
# a read-only token that lasts an hour
plaintext, token = await create_token(
    user, name="ci-readonly", abilities=["posts.read", "billing.read"], expires_in=3600,
)
```

## Scoping a token (abilities)

A token carries **abilities** — the scopes it's allowed to use. Check one with `can`:

```python
token.can("posts.read")     # True  (granted, or the token holds "*")
token.can("posts.delete")   # False (not in its abilities)
```

`"*"` grants everything; an empty ability list grants **nothing** (fail closed). Enforce a scope per
request after authenticating — `TokenGuard.token(request)` hands you the validated record:

```python
token = await TokenGuard().token(request)        # the ApiToken, or None
if token is None or not token.can("posts.delete"):
    return "Forbidden", 403
```

## Expiring a token

Pass `expires_in` (seconds) to time-box a token; `resolve_token` (and therefore `TokenGuard`) treat
an expired token as invalid — the request is simply unauthenticated:

```python
plaintext, token = await create_token(user, expires_in=86400)   # 24h
token.is_expired()                                              # False now, True after 24h
await resolve_token(expired_plaintext)                          # → None (rejected)
```

Omit `expires_in` for a non-expiring token — unless config `api_tokens.expiration` (minutes) is set, in
which case that's the default lifetime applied whenever a caller doesn't pass `expires_in` explicitly
(an explicit `expires_in` always overrides it). `create_token` **validates at mint** — a positive
`expires_in` (or `None`) and a non-empty set of non-empty ability strings — and raises `ValueError`
rather than store a footgun token (a bare string like `abilities="posts.read"` is treated as one
ability, not split into characters).

Expired tokens are already rejected by `resolve_token`, but their rows linger. Reclaim them with a
periodic prune (wire it to a [scheduled command](../console.md)):

```python
from arvel.auth.tokens import prune_expired_tokens

removed = await prune_expired_tokens()   # deletes only past-expiry tokens; non-expiring rows are kept
```

## Authenticating a request

The client sends the token as a bearer header:

```http
GET /api/projects
Authorization: Bearer 9f3a…
```

`TokenGuard` reads that header and resolves the owning user's id:

```python
from arvel.auth.tokens import TokenGuard

async def api_handler(request):
    user_id = await TokenGuard().user_id(request)   # the tokenable_id, or None
    if user_id is None:
        return "Unauthorized", 401
    user = await User.find(user_id)
    ...
```

If you have a plaintext token in hand and want the record directly, `resolve_token` looks it up by
hash:

```python
from arvel.auth.tokens import resolve_token

record = await resolve_token(plaintext)    # ApiToken or None
```

Tokens live in the `api_tokens` table — `name`, the hashed `token`, `tokenable_id` (the owner),
`abilities` (JSON scopes), `expires_at`, and `last_used_at` (all nullable). Add it in a migration
(`ApiToken.__table__` describes it).

## Tracking last use

`resolve_token` (and therefore anything that authenticates via it) stamps `last_used_at` — but
**throttled**: at most once per config `api_tokens.last_used_throttle` seconds (default 60), not on
every single request. Stamping it on every request would add a database write to every authenticated
call on a hot endpoint; the throttle trades a little staleness for far fewer writes. Lower the
throttle (or set it to `0`) if you need per-request precision.

## `current_access_token()` and scoping a route by ability

Inside a token-authenticated request, `current_access_token()` returns the active `ApiToken` (set by
`TokenGuard` the moment it resolves a valid bearer token) and `token_can(ability)` checks it:

```python
from arvel.auth.tokens import current_access_token, token_can

async def delete_post(request, post_id):
    if not token_can("posts.delete"):
        return "Forbidden", 403
    token = current_access_token()   # the ApiToken itself, if you need more than .can()
    ...
```

For route-level enforcement, `abilities()`/`ability()` build a middleware class that both
authenticates the bearer token (**401** if missing/invalid/expired) and enforces its scope
(**403** if it doesn't match) — `abilities:a,b` (require **all**) and `ability:a` (require
**any**), built from explicit string args like `Authorize()` rather than parsed from a
colon-separated alias string:

```python
from arvel.auth.tokens import abilities, ability

router.get("/reports", export_report, middleware=[abilities("reports.read", "reports.export")])
router.post("/posts/{id}", update_post, middleware=[ability("posts.write", "posts.admin")])
```

## Common mistakes & gotchas

- **Expecting to recover a lost token.** You can't — only the hash is stored. If a user loses theirs,
  delete the old `ApiToken` row and **issue a new one**.
- **Showing the plaintext more than once.** `create_token` returns it a single time; display it then
  and never persist the plaintext yourself.
- **Treating tokens as less sensitive than passwords.** A bearer token *is* a credential — transmit
  it only over TLS, store it like a secret, and let users revoke (delete) it.
- **Forgetting to scope by user.** `tokenable_id` ties a token to its user; always resolve to that
  user and apply your normal [authorization](authorization.md) checks — a valid token says *who*, not
  *what they may do*.

## Why opaque tokens, not JWTs?

These tokens are **opaque** — a random lookup key, not a signed JWT carrying claims. That's a
deliberate choice for first-party auth (your own CLI, mobile app, or SPA):

- **Revocable now.** A token is a row; deleting it logs the client out *immediately* — for "sign out
  everywhere," a ban, or a leaked credential. A JWT stays valid until its `exp` no matter what, so
  early revocation means bolting a server-side denylist back on — the very statelessness JWTs exist
  to provide.
- **Nothing to leak.** An opaque token exposes no claims (a JWT payload is base64, readable by anyone
  holding it), and only its hash is stored — a table leak yields neither usable tokens nor user data.
- **No signing footguns.** No `alg=none`, no HS/RS algorithm confusion, no secret-strength or
  clock-skew edge cases — there's no signature to get wrong.
- **You already hit the database.** JWT's payoff is verifying *without* a lookup, which pays off
  across service boundaries. A single app queries its database every request anyway, so a
  hashed-token lookup is effectively free.

Reach for a **JWT** when the trade flips — cross-service or third-party verification, where a
resource server validates a token it did not itself issue. That's [SSO / OIDC](sso-oidc.md): the
identity provider signs a token with its **private key** and your app verifies it with the
provider's **public key** (asymmetric — a verifier can validate but can't mint). Same reasoning,
opposite context.

## How it works

`create_token` generates a 256-bit secret with `secrets.token_hex(32)` and stores only its SHA-256
hash, so the database never holds a usable token. Authentication hashes the presented bearer token the
same way and looks for a matching row (`resolve_token`); `TokenGuard.user_id` wraps that, reading the
`Authorization: Bearer` header and returning the matched `tokenable_id`. Because lookups are by hash,
a leaked table can't be replayed. `TokenGuard.token()` is the single choke point: it resolves the
record, stamps `last_used_at` (throttled), and sets a request-scoped `current_access_token()` — the
`abilities()`/`ability()` middleware just call it and check `.can()`.

## See also

- [Guards & Drivers](guards.md) — the token guard alongside session and OIDC guards.
- [Authentication](authentication.md) — session-based login for browsers.
- [Authorization](authorization.md) — what the authenticated token-bearer is allowed to do.
