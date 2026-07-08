# Guards & drivers

A real app rarely has just one way to log in. The browser uses a session; the mobile app sends a
bearer token; the admin console goes through Keycloak SSO. Writing each of those as a bespoke
if-branch is how auth code rots. arvel models every method as a **guard** — a small driver with one
job: look at a request, and either say "this is who it is" or "I don't recognise this." It answers in
a single, method-agnostic shape — a `Principal` — so everything downstream (resolving the user,
loading roles) is written once, no matter how the user proved themselves.

This page covers the `Principal` contract, the built-in guards, selecting the default, and
registering your own.

!!! note "Needs the `[jwt]` extra for OIDC"
    The `session` and password (`local`) guards are **core** — nothing to install. Only the
    OIDC/Keycloak guard pulls pyjwt: `uv add 'arvel[jwt]'` (full setup on [Single sign-on](sso-oidc.md)).

## One contract: `Principal`

Every guard returns a `Principal` (or `None` if the request carries no valid credentials for it):

```python
from arvel.auth.identity import Principal

p = Principal(provider="keycloak", subject="kc-abc-123", claims={"email": "ada@corp.com"})
p.provider          # which method/IdP produced it — "local", "session", "keycloak", …
p.subject           # the STABLE identifier (a sub / username) — never the email
p.claims            # the raw verified claims (a mapping)
p.email             # convenience: claims["email"] or None
p.email_verified    # convenience: a real bool (string "true"/"false" is normalised)
```

A `Principal` says *who the request claims to be* — it is **not** a `User`. Turning a verified
`Principal` into your `User` row is the next layer's job ([Identities & account linking](identities.md)).
That split is the whole point: guards worry about *proof*, the user provider worries about *identity*.

## The guard manager

Guards are resolved through `GuardManager` — a driver manager (the same pattern as cache and
storage). Ask it for a guard by name; it builds and caches it:

```python
from arvel.auth.guards import GuardManager

guards = GuardManager()
guards.guard("session")     # the default — reflects the logged-in user
guards.guard("local")       # password verification
guards.guard("oidc")        # OIDC / Keycloak (needs the [jwt] extra)
guards.guard()              # the configured default
```

### `session` — the established session

`SessionGuard` reports whoever is already logged in (the request-scoped `current_user`), as a
`Principal` with `provider="session"`:

```python
principal = await GuardManager().guard("session").verify(request)
# Principal(provider="session", subject="42")  — or None if nobody is logged in
```

### `local` — password verification

`LocalGuard` checks an `email`/`username` + `password` from the submitted form against the stored
credential hash (see [Authentication](authentication.md)):

```python
guard = GuardManager().guard("local")
principal = await guard.verify(request)              # reads the form, returns Principal("local", …) or None

# or check a known pair directly:
principal = await guard.attempt("ada@example.com", "secret")
```

## Choosing the default guard

`guards.guard()` (no name) resolves the default, which comes from config — `auth.default_guard`,
falling back to `"session"`:

```python
# config/auth.py
auth = {
    "default_guard": "session",   # browser sessions by default
}
```

## Registering your own guard

A guard is anything with `async def verify(self, request) -> Principal | None`. Register a creator
with `extend(name, creator)` — the creator receives the application and returns the guard:

```python
from arvel.auth.identity import Principal

class HeaderApiKeyGuard:
    async def verify(self, request):
        key = request.header("x-api-key") if hasattr(request, "header") else None
        if not key or not await is_valid(key):
            return None
        return Principal(provider="apikey", subject=await owner_of(key))

guards = GuardManager()
guards.extend("apikey", lambda app: HeaderApiKeyGuard())
await guards.guard("apikey").verify(request)
```

That's the whole extension surface — no base class to subclass, just the `verify` shape.

## Common mistakes & gotchas

- **Treating a `Principal` as a `User`.** It isn't one. A guard only *authenticates*; pass the
  `Principal` to the [user provider](identities.md) to get (or create/link) the actual `User`.
- **`subject` is not the email.** Use `subject` (the stable `sub`/username) as the identity key;
  emails change and aren't unique across providers.
- **Asking for a guard whose extra isn't installed.** Federated/heavy drivers load lazily; requesting
  one without its package raises a clear `MissingExtraError` telling you which `uv add 'arvel[…]'`
  to run. The `oidc` driver needs `arvel[jwt]`.
- **Expecting unknown drivers to exist.** `guard("nope")` with no built-in `create_nope_driver` and
  no `extend("nope", …)` raises `MissingExtraError` — register it first.

## How it works

`GuardManager` extends the shared `Manager` base: `guard(name)` (an alias for `driver(name)`)
resolves a driver once and caches it. Resolution dispatches to a registered `extend` creator if one
exists, else to a `create_<name>_driver` method (`create_session_driver`, `create_local_driver`,
`create_oidc_driver`); anything unknown raises `MissingExtraError`. The federated drivers do their
heavy imports **inside** those creators, so importing the guard module never drags pyjwt/httpx into
the light core — the `import arvel` startup contract holds.

## See also

- [Authentication](authentication.md) — the `local` guard and the session in practice.
- [Identities & account linking](identities.md) — turning a `Principal` into a `User`.
- [Single sign-on (OIDC / Keycloak)](sso-oidc.md) — the `oidc` guard in full.
- [API tokens](api-tokens.md) — the token guard for bearer-token APIs.
