# Authentication & Security

This section covers everything about *who can do what* in an arvel app — **authentication** (proving
who a user is), **authorization** (deciding what they may do), and the cryptographic primitives
(password hashing, value encryption) underneath. Start here: this page gives you the mental model,
helps you **pick the right auth mechanism**, gets you protecting a route in five minutes, and points
at the deep-dive page for each mechanism.

Almost every "auth bug" you've ever debugged comes from quietly conflating three different questions:

- **Who is this user?** — their durable identity (the row in your `users` table).
- **How did they prove it?** — a password, a Google login, a Keycloak SSO token, an API key.
- **What are they allowed to do?** — their roles and permissions.

Smush those together and you get the classic messes: a user who can't log in with Google because
they signed up with a password; an SSO migration that means re-creating every account; an admin role
that silently came from an identity provider nobody audited. arvel keeps the three **separate**, and
joins them with two small, well-defined seams — so each can change without disturbing the others.

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

Two rules make this work, and they're the whole philosophy of the section:

1. **Identity is decoupled from authentication.** Your `User` record never stores *how* someone logs
   in. A person can have a password *and* a Google login *and* a Keycloak account — all three resolve
   to the same `User`. Adding or removing a login method is a row, not a migration.
2. **The identity provider's vocabulary is translated at the door, never modeled inside arvel.** An
   external `sub` claim becomes an [`AuthIdentity`](identities.md) link; an external `groups` claim
   becomes arvel [`Role`s](authorization.md) through a mapping. There is exactly one authorization
   vocabulary — `Role` and `Permission` — and everything an IdP asserts is *converted* into it.

Everything else is an application of those two rules.

## Choosing an auth mechanism

"Authentication" isn't one thing — it's a family of mechanisms for different clients. Pick by **who's
calling and how they prove it**:

| Your situation | Use | Why | Deep dive |
|----------------|-----|-----|-----------|
| Server-rendered web app, users log in with a **form** in a browser | **Session** (`SessionGuard`) | A cookie the browser sends automatically; server tracks the session. Add remember-me + 2FA. | [Authentication](authentication.md) |
| **API, SPA, mobile, or CLI** — a non-browser client that puts a credential in a header | **API token** (personal access token) | An opaque bearer token you issue per user, sent as `Authorization: Bearer …`, with per-token abilities + expiry. | [API Tokens](api-tokens.md) |
| **Machine-to-machine** / service accounts | **API token** with abilities | Same tokens, scoped to just the abilities that service needs. | [API Tokens](api-tokens.md) |
| "**Log in with Google / GitHub**" (social login) | **OAuth 2.0** (`OAuthProvider`) | The redirect→callback→code-exchange flow that logs the user in *through* the provider and gets their profile. | [OAuth2](oauth.md) |
| "**Log in with our company account**" — enterprise SSO (Keycloak, Okta, Entra/Azure AD) | **OIDC** (`OAuthProvider` to obtain + `OidcGuard` to validate) | OIDC = OAuth2 + a standard identity layer; you get a signed `id_token` with identity claims. | [SSO / OIDC](sso-oidc.md) |
| Your **API validates a JWT** an upstream gateway/IdP already issued | **OIDC guard** (`OidcGuard`, validate mode) | Verifies the token's signature against the IdP's JWKS and turns it into a `Principal` — no redirect. | [SSO / OIDC](sso-oidc.md) |

Two decisions capture most of it:

- **Browser vs non-browser** → *session* for browsers, *API token* for everything else. (A SPA served
  from your own domain can use either — sessions if it shares the domain, tokens if it's cross-origin.)
- **Do you run the login, or does someone else?** → *you* run it (password / API token) vs a *provider*
  runs it (OAuth for social, OIDC for enterprise SSO). These compose: a session app can offer
  "log in with Google" *and* a password form, both resolving to the same `User`.

You rarely pick just one. A typical app uses **sessions** for its web UI, **API tokens** for its
public API, and **OAuth/OIDC** as extra login buttons — all landing on the same `User` and the same
[authorization](authorization.md) checks.

## Protect your first route in 5 minutes

Make your user model authenticatable, log someone in, protect a route, and read the user back.

**1. The user model** — mix in `Authenticatable` (login) and `HasRoles` (permissions):

```python
# app/models/user.py
from arvel import Model
from arvel.auth import Authenticatable, HasRoles

class User(Model, Authenticatable, HasRoles):
    __fields__ = {"email": str, "name": str, "password": str}
    __fillable__ = ["email", "name"]
    __casts__ = {"password": "hashed"}   # a raw password is argon2-hashed on assignment
```

**2a. Session login** (browser app) — verify the password the timing-safe way, then start a session:

```python
from arvel.auth import verify_credentials
from arvel.auth.guards import SessionGuard

async def login(request):
    data = await request.form()
    user = await User.where("email", data["email"]).first()
    if not await verify_credentials(user, data["password"]):   # dummy-hash on a missing user; off-loop
        abort(401, "Invalid credentials")
    await SessionGuard().login(user, request)                  # rotates the session id, persists the user
    return redirect("/dashboard")
```

**2b. Or token login** (API) — verify, then mint a bearer token (shown once):

```python
from arvel.auth import verify_credentials
from arvel.auth.tokens import create_token

async def token_login(request):
    data = await request.json()
    user = await User.where("email", data["email"]).first()
    if not await verify_credentials(user, data["password"]):
        abort(401, "Invalid credentials")
    plaintext, _ = await create_token(user, name="mobile-app")  # the client stores `plaintext`
    return {"token": plaintext}
```

**3. Protect a route** with the `auth` middleware (401 if not authenticated), and read the user:

```python
from arvel import Route
from arvel.auth import current_user

async def me(request):
    user = current_user.get()          # the authenticated User, established by the guard middleware
    return {"email": user.email}

Route.get("/me", me, middleware=["auth"])                      # ENFORCES: 401 unless authenticated
Route.get("/api/me", me, middleware=["auth"]).secure("bearer") # …and documents the scheme in OpenAPI
```

That's a working, secure login. `verify_credentials` closes the two classic password-check bugs (user
enumeration by timing + blocking the event loop); `SessionGuard.login` rotates the session id (fixation
defense); tokens are hashed at rest. Everything below layers depth onto this.

## What each mechanism *is* (in one paragraph each)

- **Sessions** — the browser stores an opaque session-id cookie; the server keeps the session state.
  Stateful, revocable instantly (drop the server record), and the natural fit for a server-rendered
  app. Comes with CSRF protection and session-fixation defense. See [Authentication](authentication.md).
- **API tokens** — high-entropy random strings you issue per user; the client sends one as a bearer
  header. arvel stores **only a SHA-256 hash**, so a DB leak exposes nothing usable, and each token
  carries **abilities** (scopes) + an optional expiry. Deliberately **opaque, not JWTs** — so you can
  revoke one instantly by deleting its row (a self-contained JWT can't be un-issued). See
  [API Tokens](api-tokens.md).
- **OAuth 2.0** — a *delegation* protocol. "Log in with Google" redirects the user to Google, who sends
  back an authorization code you exchange for tokens + the user's profile. You never see their Google
  password. See [OAuth2](oauth.md).
- **OIDC** — OAuth 2.0 **plus a standardized identity layer**. Where plain OAuth gets you *access*,
  OIDC gets you a signed **`id_token`** with identity claims (`sub`, `email`, `groups`). This is what
  enterprise SSO (Keycloak/Okta/Entra) speaks. arvel splits it into *obtain* (`OAuthProvider` runs the
  redirect) and *validate* (`OidcGuard` verifies the JWT). See [SSO / OIDC](sso-oidc.md).
- **Guards** — the pluggable engine under all of the above. Every mechanism is a *guard driver* that
  turns a request into a `Principal`; you can register your own. See [Guards & Drivers](guards.md).

## The confusing parts, cleared up

- **Token vs session — which and why.** A *session* is server-side state keyed by a cookie: great for
  browsers, instantly revocable, but the server must hold the state. A *token* is a self-describing
  credential the client sends on every request: great for APIs and cross-origin clients, no cookie
  needed. Rule: **browser → session, everything else → token.** arvel's tokens are opaque (hashed in
  the DB), so they keep the session's best trait — instant revocation — which a stateless JWT gives up.
- **OAuth vs OIDC — they're not alternatives.** OAuth answers "can this app *act* on the user's
  behalf?" (authorization). OIDC adds "…and here is *who the user is*, signed" (authentication). For a
  social/SSO login you usually want **both**: `OAuthProvider` runs the OAuth redirect and hands you an
  `id_token`; the OIDC verifier validates it. If a page says "use OAuth to log in," it almost always
  means the OIDC-flavored flow. Don't build identity on plain OAuth access tokens — they're not proof
  of *who* logged in.
- **"Obtain a token" vs "validate a token."** Two different jobs people conflate. *Obtaining* is the
  browser redirect dance (`OAuthProvider`, `[oauth]` extra). *Validating* is an API checking a bearer
  JWT it was handed (`OidcGuard`, `[jwt]` extra). You need the first to *log users in*, the second to
  *protect an API* behind an existing IdP.
- **Expiry & rotation.** Access tokens should be short-lived; pair them with **rotating refresh
  tokens** (the refresh flow in [Routes & Flows](routes-and-flows.md)) so a leaked access token dies
  quickly and each refresh invalidates the last. Sessions expire via cookie lifetime + server TTL.
- **Callbacks & redirects.** The OAuth `redirect_uri` you send must **exactly** match one registered
  with the provider — scheme, host, port, path, trailing slash. A mismatch is the #1 OAuth error (see
  [Troubleshooting](#troubleshooting)).

## Security

Auth is where a small mistake becomes a real vulnerability. arvel's defaults are safe; these are the
things to get right and the anti-patterns to never ship.

**Secrets & storage**
- **Never commit secrets.** `APP_KEY`, OAuth client secrets, and IdP credentials go in the environment,
  not the repo. `APP_KEY` keys signed URLs, remember-me cookies, and encryption — [rotate it with a
  plan](configuration.md), never casually.
- **Passwords are argon2id-hashed** (never stored or logged in plaintext); cast the column `"hashed"`
  so a raw password is hashed on assignment and can never reach the DB. See [Hashing](../hashing.md).
- **API tokens and reset tokens are stored hashed** — the plaintext exists only in the client's hand /
  the emailed link. A DB leak exposes nothing usable.

**Verifying credentials**
- **Use `verify_credentials` / `Auth.attempt`, never an inline `Hasher().check`.** The naive
  `if user is None or not Hasher().check(pw, user.password)` leaks two things: it *skips the hash* when
  the user is missing (an unknown email answers faster — a **user-enumeration timing oracle**), and the
  sync `check` **blocks the event loop**. `verify_credentials` burns a dummy hash for a missing user
  and runs off-loop. **Never compare passwords with `==`.**

**Tokens & JWTs**
- **Short-lived access tokens + rotating refresh tokens.** Don't issue a long-lived access token you
  can't revoke.
- **JWT algorithm safety.** arvel **rejects a JWT whose algorithm list mixes symmetric and asymmetric
  families** (the `alg` confusion attack, where an attacker signs an HS256 token with your *public* key
  as the HMAC secret). Configure a single, explicit algorithm family for your IdP.
- **Validate signatures against the IdP's JWKS**, and check `iss`/`aud`/`exp`. `OidcGuard` does this.

**Sessions & cookies**
- **CSRF is on for the web group.** State-changing session requests are checked (double-submit token +
  origin/referer). Don't disable it except for a genuine webhook endpoint. See [CSRF](../csrf.md).
- **Session fixation is defended** — `SessionGuard.login` rotates the session id before persisting the
  user id. Do the login through the guard, not by hand-setting the session.
- The session cookie is `HttpOnly` + `Secure`; the CSRF cookie is intentionally *not* `HttpOnly` (it's
  the double-submit token, not a secret).

**OAuth / OIDC**
- **Exact `redirect_uri` match** — an over-broad or mismatched redirect is an open-redirect / token-theft
  vector. Register the precise URI.
- **The OAuth `state` parameter is CSRF protection for the flow** — arvel handles it; don't strip it.
- **Vet what an IdP claim maps to.** A `groups` claim that maps to an admin `Role` is a privilege path;
  never map an unvetted claim to `*` or an admin role. See [IdP → Roles](idp-roles.md).

**Anti-patterns — never do these**
- ❌ **Never** store `google_id`/`how-they-log-in` on the `User` row — use [identities](identities.md).
- ❌ **Never** hand out the `*` (super-admin) permission to anything an IdP claim can reach unvetted.
- ❌ **Never** put a bearer token or password in a URL, a log line, or a trace attribute.
- ❌ **Never** "document" a route as protected without the actual guard middleware — a `.secure()`
  marker documents the scheme; the *enforcement* is the [middleware](providers-and-middleware.md).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| **401 on a route you thought was protected/open** | The guard middleware isn't applied, or the `user_resolver`/token guard isn't wired, or no `Authorization: Bearer` header was sent. | Add the guard middleware (`middleware=["auth"]`) — `.secure("bearer")` only *documents* the scheme, it doesn't enforce; confirm the request carries the credential; check the guard is [registered](guards.md). |
| **`Authorize("posts.updte")` silently 403s everything** | A typo'd ability never matches, so the Gate always denies. | Assert your abilities exist at boot (`Gate.has_ability`); see [providers-and-middleware](providers-and-middleware.md). |
| **JWT "invalid signature" / verification fails** | Wrong signing key or JWKS URL; an **algorithm mismatch** between the IdP and your guard; or the guard rejecting a mixed HS+asymmetric `alg` list. | Point the guard at the IdP's JWKS endpoint; pin a single algorithm family; confirm `iss`/`aud`. See [SSO / OIDC](sso-oidc.md). |
| **"Token expired"** | Access token past its `exp`. | Refresh with the rotating **refresh token** (don't just re-issue); if there's no refresh, re-authenticate. See [Routes & Flows](routes-and-flows.md). |
| **OAuth `redirect_uri_mismatch` / `invalid redirect`** | The `redirect_uri` you send doesn't **exactly** match one registered with the provider (scheme/host/port/path/trailing slash). | Register the exact callback URL with the provider and use the identical string. |
| **OAuth `state` mismatch / CSRF error on callback** | The `state` didn't round-trip (session dropped between redirect and callback, or a proxy stripped it). | Ensure the session cookie survives the redirect; don't remove the `state` param. |
| **A password user can't "log in with Google"** (or vice-versa) | The Google identity was never linked to the existing `User`. | Link login methods as [identities](identities.md) on the same user — don't create a second account. |
| **419 "page expired" on a form POST** | Missing/invalid **CSRF token** on a session request. | Include the CSRF token (`csrf_field()` / the `XSRF-TOKEN` cookie for a SPA). See [CSRF](../csrf.md). |
| **Login is slow / unknown emails respond faster** | An inline `Hasher().check` (blocking + enumeration oracle). | Switch to `verify_credentials`. |

## Full reference — the deep-dive pages

Start at the top and read down, or jump to what you need:

| Page | What you'll learn |
|------|-------------------|
| [Authentication](authentication.md) | Passwords, sessions, `SessionGuard`, the local guard, brute-force lockout |
| [Guards & Drivers](guards.md) | The `Principal` contract, the guard manager, registering your own guard |
| [API Tokens](api-tokens.md) | Issuing/validating bearer tokens, abilities, expiry, `TokenGuard` |
| [SSO / OIDC](sso-oidc.md) | Obtaining vs validating a token; the `oidc` guard; claims; offline testing |
| [OAuth2 Social Login](oauth.md) | The redirect/callback flow; configuring Google/GitHub/Keycloak |
| [Identities & Account Linking](identities.md) | One person, many login methods — safely linked |
| [Mapping IdP Groups to Roles](idp-roles.md) | Let Keycloak/Okta groups drive arvel roles |
| [Authorization](authorization.md) | Roles, permissions, gates, policies, impersonation |
| [Two-Factor Authentication](two-factor.md) | TOTP second factor + single-use recovery codes |
| [Password Reset](password-reset.md) | The reset-link flow; pruning expired tokens |
| [Email Verification](email-verification.md) | Verify-email flow + the `verified` route guard |
| [Routes & Flows](routes-and-flows.md) | Wiring login/logout, refresh-token rotation, reset, verification |
| [Providers & Middleware](providers-and-middleware.md) | Registering auth services + the `auth`/`guest`/`verified` guards |
| [Configuration](configuration.md) | Every auth config key + the `security` audit-log channel |
| [Hashing](../hashing.md) · [Encryption](../encryption.md) | The crypto primitives underneath |

## See also

- [Service Container](../container.md) — guards and the user provider are resolved from the container.
- [Middleware](../middleware.md) — where the active user is established for each request.
- [Validation](../validation.md) — validating login and registration input.
- [CSRF](../csrf.md) — the cross-site-request-forgery protection on the web group.
