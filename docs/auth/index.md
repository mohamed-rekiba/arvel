# Authentication & Authorization

Almost every "auth bug" you've ever debugged comes from quietly conflating three different
questions:

- **Who is this user?** — their durable identity (the row in your `users` table).
- **How did they prove it?** — a password, a Google login, a Keycloak SSO token, an API key.
- **What are they allowed to do?** — their roles and permissions.

Smush those together and you get the classic messes: a user who can't log in with Google because
they signed up with a password; an SSO migration that means re-creating every account; an admin
role that silently came from an identity provider nobody audited. arvel keeps the three **separate**,
and joins them with two small, well-defined seams — so each one can change without disturbing the
others.

## The mental model

```
   How they prove it            Who they are               What they may do
  ┌───────────────────┐       ┌──────────────┐           ┌────────────────────┐
  │  AUTHENTICATION   │       │   IDENTITY   │           │   AUTHORIZATION    │
  │  guard drivers    │──────▶│     User     │──────────▶│  roles/permissions │
  │  password · OIDC  │       │  (your table)│           │  Gate · policies   │
  │  token · session  │       └──────────────┘           └────────────────────┘
  └───────────────────┘              ▲                            ▲
          │ Principal                │ AuthIdentity               │ claim→role map
          │ (provider, subject,      │ (provider, subject)        │ (group/role claim
          │  claims)                 │   → user                   │   → arvel Role)
          └──────────────────────────┘                            │
                  translate identity                       translate authorization
```

Two rules make this work, and they're the whole philosophy of this section:

1. **Identity is decoupled from authentication.** Your `User` record never stores *how* someone
   logs in. A person can have a password *and* a Google login *and* a Keycloak account — all three
   resolve to the same `User`. Adding or removing a login method is a row, not a migration.

2. **The identity provider's vocabulary is translated at the door, never modeled inside arvel.**
   An external `sub` claim becomes an [`AuthIdentity`](identities.md) link; an external `groups`
   claim becomes arvel [`Role`s](authorization.md) through a mapping. arvel has exactly one
   authorization vocabulary — `Role` and `Permission` — and everything an IdP asserts is *converted*
   into it. There is no second "group" concept competing with `Role`.

Everything else in this section is an application of those two rules.

## A 30-second taste

```python
from arvel.auth import Authenticatable, HasRoles
from arvel import Model

class User(Model, Authenticatable, HasRoles):
    __fields__ = {"email": str, "name": str}
    __fillable__ = ["email", "name"]
```

```python
# Authentication — verify a password and start a session
from arvel.auth import AuthManager

auth = AuthManager()
if await auth.attempt({"email": "ada@example.com", "password": "secret"}, find_user):
    user = auth.user()            # logged in

# Authorization — ask what they may do
if await user.has_permission_to("posts.publish"):
    ...
```

That same `User` could just as easily have arrived via a Keycloak SSO token instead of a password —
the authorization check on the last line wouldn't change at all. That's the decoupling paying off.

## What's in this section

Start at the top and read down, or jump to what you need:

| Page | What you'll learn |
|------|-------------------|
| [Authentication](authentication.md) | Passwords, sessions, logging users in and out |
| [Guards & drivers](guards.md) | The pluggable engine behind every login method |
| [Identities & account linking](identities.md) | One person, many login methods — safely linked |
| [Single sign-on (OIDC / Keycloak)](sso-oidc.md) | Log users in through an identity provider |
| [OAuth2 social login](oauth.md) | "Log in with Google/GitHub/Keycloak" — the redirect/callback flow |
| [Authorization: roles & permissions](authorization.md) | Roles, permissions, gates, and policies |
| [Mapping IdP groups to roles](idp-roles.md) | Let Keycloak groups drive arvel roles |
| [API tokens](api-tokens.md) | Bearer tokens for APIs and machine-to-machine |
| [Two-factor authentication](two-factor.md) | TOTP second factor + recovery codes |
| [Routes & flows](routes-and-flows.md) | Wiring login/logout, refresh tokens, password reset, email verification |
| [Wiring it up: providers & middleware](providers-and-middleware.md) | Registering auth services + protecting routes |

## See also

- [Service Container](../container.md) — guards and the user provider are resolved from the container.
- [Middleware](../middleware.md) — where the active user is established for each request.
- [Validation](../validation.md) — validating login and registration input.
