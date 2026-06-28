# Identities & account linking

Ada signs up with a password. Six months later your company adopts Keycloak and she clicks "Log in
with SSO." Is that a *new* account, or the same Ada? It had better be the same one — same profile,
same posts, same permissions. The only thing that changed is *how she proved who she is*.

That's the job of this layer. A `User` is the durable person; an **`AuthIdentity`** is one way that
person can log in. One user can have many identities — a password, a Keycloak login, a GitHub login —
and every one of them resolves to the same `User`. Adding or removing a login method is a row, not a
migration. This page covers the `AuthIdentity` seam, how a verified login becomes a `User`, and the
two rules that keep linking safe.

## The seam: `AuthIdentity`

An `AuthIdentity` links an external `(provider, subject)` to a local user:

```python
from arvel.auth.identity import AuthIdentity
# table "auth_identities": provider, subject, user_id, credential
```

- `provider` — `"local"`, `"keycloak"`, `"github"`, …
- `subject` — the **stable** identifier from that provider (the OIDC `sub`, or the local username/email
  used as the credential key). Never a display name.
- `user_id` — the local `User` it resolves to.
- `credential` — the hashed secret for the `local` provider; empty for federated logins (the IdP holds
  the secret).

Because the link is `(provider, subject) → user` and a user can own many rows, "Ada with a password
*and* Keycloak" is just two `AuthIdentity` rows pointing at one `User`.

## From a verified login to a `User`

A [guard](guards.md) authenticates a request and hands you a `Principal`. `UserProvider.resolve`
turns that `Principal` into a `User`:

```python
from arvel.auth.identity import UserProvider, DbIdentityStore

provider = UserProvider(
    DbIdentityStore(User),                       # your app's User model
    trusted_email_providers={"keycloak"},        # who may assert a verified email (see below)
    jit=True,                                     # auto-create users on first SSO login
    user_factory=create_user_from_claims,        # how to build that new user
)

user = await provider.resolve(principal)         # the User, or None
```

`resolve` follows a deliberate order:

1. **Known identity → its user.** If `(provider, subject)` already exists, return that user. Done.
2. **Link by verified email.** If it's a new identity *and* the token carries a **verified** email
   *and* the provider is trusted to assert email, link the new identity to the existing user with
   that email — that's the password-user clicking SSO for the first time.
3. **Just-in-time provisioning.** Otherwise, if `jit=True`, create a fresh user via your
   `user_factory(principal)` and link it.
4. **Otherwise** → `None` (no safe way to resolve).

!!! danger "Linking is gated on a *verified* email from a *trusted* provider"
    Step 2 is the #1 account-takeover boundary. If you linked on any email an IdP asserted, anyone
    who could set `email=ceo@yourco.com` at *some* provider you accept would inherit the CEO's
    account. arvel links **only** when the claim says `email_verified` **and** the provider is in
    your `trusted_email_providers` set. An unverified or untrusted email never auto-links — it falls
    through to JIT (a brand-new account) or `None`. The join key is always the stable `subject`,
    never the email.

## Configuration

In a real app you don't build `UserProvider` by hand — it's registered as `auth.user_provider` from
config:

```python
# config/auth.py
auth = {
    "user_model": "app.models.User",         # your Authenticatable model
    "trusted_email_providers": ["keycloak"], # providers allowed to assert a verified email
    "jit": True,                             # auto-provision on first federated login
}
```

If `auth.user_model` isn't set, identity resolution is simply disabled (the binding returns `None`) —
nothing links until you opt in.

## Unlinking — and the lockout guard

Removing a login method is `unlink`, with one invariant baked in: **a user can never remove their
last remaining credential.**

```python
await provider.unlink(user, "github", "gh-12345")   # fine — she still has password + keycloak

await provider.unlink(user, "local", "ada@example.com")
# raises LastCredentialError if that was the only identity left
```

This makes self-service "manage your logins" safe by construction — a user can't accidentally lock
themselves out. (Disabling a user is a separate, explicit action, not a side effect of unlinking.)

## Common mistakes & gotchas

- **Linking on an unverified email.** Don't. It's account takeover. Keep `trusted_email_providers`
  tight and rely on `email_verified` — arvel already enforces both, so don't reach around it.
- **Using the email as the identity key.** `subject` is the stable `sub`/username; emails change and
  collide across providers. Match on `(provider, subject)`.
- **Expecting JIT by default.** It's off unless you set `jit=True` *and* provide a `user_factory`.
  Without it, an unknown login resolves to `None` rather than silently creating accounts.
- **Forgetting the table.** Add an `auth_identities` table in a migration (`AuthIdentity.__table__`
  describes it: `provider`, `subject`, `user_id`, `credential`).

## How it works

`UserProvider` holds an `IdentityStore` — the default `DbIdentityStore` runs the lookups against the
`auth_identities` table and your `User` model (`find`, `user_for`, `user_by_email`, `link`,
`count_for_user`, `unlink`). `resolve` applies the four-step policy above; `unlink` checks
`count_for_user` and refuses to drop the last one (`LastCredentialError`). The store is an injectable
protocol, so tests swap in an in-memory fake and exercise the *policy* without a database. Identities
are real, persisted rows — unlike IdP-derived [roles](idp-roles.md), which are ephemeral.

## See also

- [Guards & drivers](guards.md) — where the `Principal` that `resolve` consumes comes from.
- [Single sign-on (OIDC / Keycloak)](sso-oidc.md) — the federated logins you link.
- [Authentication](authentication.md) — the `local` credential stored on an identity.
- [Mapping IdP groups to roles](idp-roles.md) — the *authorization* counterpart to this seam.
