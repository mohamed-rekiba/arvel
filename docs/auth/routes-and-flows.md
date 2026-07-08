# Routes & Flows

The rest of this section gave you the building blocks — guards, the session, identities, roles, tokens.
What it deliberately *didn't* give you is a set of ready-made `/login` and `/logout` routes. That's by
design: arvel ships authentication **primitives, not a login scaffold**, so you stay in control of
your URLs, templates, validation, and responses. This page is the recipe book — it shows how to wire
the common flows from those primitives: session login/logout, OAuth/SSO login (the redirect &
callback), refresh-token rotation for APIs, password reset, and email verification.

## Session login & logout

A login route is just: validate the form, `attempt` the credentials, and on success hand off to
`SessionGuard.login` — which rotates the session id **and** persists the user id so later requests
stay logged in (see [Authentication](authentication.md#logging-in-over-http-sessionguard)):

```python
from arvel.auth import AuthManager
from arvel.auth.guards import SessionGuard

auth = AuthManager()

async def find_user(credentials):
    return await User.where(email=credentials["email"]).first()

async def login(request):
    credentials = await request.form()
    if await auth.attempt(credentials, find_user):
        await SessionGuard().login(auth.user(), request)   # rotate id + persist user id (see below)
        return redirect("/dashboard")
    return "Invalid credentials", 401

async def logout(request):
    await SessionGuard().logout(request)   # clears remember + invalidates the session + current_user
    return redirect("/")
```

Register them as ordinary routes. CSRF-protect the login form like any other session POST (see
[Middleware](../middleware.md)).

### Rotate the session on login (fixation defence)

A **session-fixation** attack plants a known session id in the victim's browser *before* they log in,
then rides that same id afterwards. The defence is to **issue a new session id the moment privilege
changes**: `SessionGuard.login` calls `regenerate_session(request)` internally, **before** writing the
persisted user id, so a pre-login (possibly attacker-fixed) id is never reused for an authenticated
session; `SessionGuard.logout` calls `invalidate_session(request)`. Reach for the lower-level helpers
directly only if you're composing your own login/logout outside `SessionGuard`:

- `regenerate_session(request)` — new id, **keeps** the session data (cart, flash, CSRF token).
- `invalidate_session(request)` — new id, **drops** all data (a clean logout).

`StartSession` does the rest: it issues the rotated cookie (`HttpOnly`, `SameSite=Lax`, `Secure` by
default, and — when Secure — the **`__Host-` prefix** that browsers only accept with `Secure`+`Path=/`+no
`Domain`, blocking cookie-injection from a sibling subdomain) on the way out, and forgets the old id
from the store. In plain-HTTP local dev, construct it with `StartSession(secure=False)` so the cookie
isn't HTTPS-gated (the name falls back to plain `session`, since `__Host-` requires Secure).

!!! warning "Upgrading a live Secure deployment rotates the cookie name"
    Turning on the `__Host-` prefix (the default when Secure) changes the cookie name from `session`
    to `__Host-session`, so the server stops reading any pre-existing `session` cookie — every
    already-logged-in user starts a fresh session **once** on the first request after deploy. This is
    benign (fail-safe), but if a fleet-wide re-login is disruptive, roll it out with
    `StartSession(host_prefix=False)` and flip it on later.

!!! note "Cookie rotation is emitted on the success path"
    The new/rotated `Set-Cookie` is written after the response is built. If a handler *raises*, the
    framework renders the error response without it — but this is fail-closed: `StartSession` has
    already forgotten the old id server-side, so the client just starts a fresh session next request,
    never riding a stale id. A login/logout that errors mid-flight only desyncs the cookie.

### Stay logged in ("remember me")

A session ends when the browser session does. To keep a user logged in across restarts, issue a
**remember token** — a long-lived cookie backed by a hashed, single-use token (the `selector:validator`
pattern: only a hash is stored, and the validator rotates on every use so a stolen-and-replayed cookie
is detected and the token destroyed).

`SessionGuard.login`'s `remember=` flag issues it on login; `SessionGuard.logout` always clears it:

```python
from arvel.auth.guards import SessionGuard

async def login(request):
    form = await request.form()
    if await auth.attempt(form, find_user):
        await SessionGuard().login(auth.user(), request, remember=bool(form.get("remember")))
        return redirect("/dashboard")
    return "Invalid credentials", 401

async def logout(request):
    await SessionGuard().logout(request)   # clears the remember cookie/token too
    return redirect("/")
```

(Composing your own flow instead of `SessionGuard`? `arvel.auth.remember.remember(request, user)` /
`forget_remember(request)` are the same primitives, callable directly.)

Then add the `RememberMe` middleware to the **web** group, **after** `AuthenticateMiddleware`. When a
request arrives with no logged-in user but a valid remember cookie, it logs the user in for that
request, rotates the cookie, and seeds the session so later requests authenticate from the session:

```python
from arvel.auth.remember import RememberMe

# user_loader turns a stored id back into your User model
RememberMe(lambda uid: User.find(uid))             # secure=False for plain-HTTP dev
```

A forged, expired, or already-used cookie is rejected (fail closed) and cleared. On a password change
or "log out everywhere", call `clear_all_remember_tokens(user.id)` to revoke every remembered device.

## Sessions & devices: log out everywhere

When a user changes their password — or clicks "sign out of all devices" after losing a laptop —
revoke every **persistent** credential so no device can silently come back. `logout_everywhere`
revokes the lot in one call: refresh tokens, remember-me tokens, and personal API tokens.

```python
from arvel.auth.devices import logout_everywhere
from arvel.http.session import invalidate_session

async def change_password(request):
    user = request.user()
    user.password = Hasher().make((await request.form())["password"])
    await user.save()
    await logout_everywhere(user)      # kill every device's persistent re-auth
    invalidate_session(request)        # drop THIS session too — force a fresh login
    return redirect("/login")
```

!!! note "What 'everywhere' covers"
    `logout_everywhere` revokes the long-lived credentials that let a device re-authenticate **and**
    bumps the session generation, so live web sessions are evicted too wherever `EnsureSessionCurrent`
    is wired (see below); without that middleware, live sessions instead lapse at the session lifetime
    (`StartSession(lifetime=...)`, default 2h). A **bearer JWT already issued** (an access token from
    the SSO/JWT guards) is stateless and stays valid until its own `exp` — revoking refresh tokens
    stops *new* ones being minted, not outstanding short-lived ones. So for token APIs, size the
    access-token lifetime for the residual window you can tolerate.

### Log out other devices (live sessions)

To drop a user's *other* live sessions while keeping the current one (and to make
`logout_everywhere` evict live sessions), arvel tracks a per-user session **generation**: each session
is stamped with it at login, and a small middleware logs out any session whose stamp falls behind.

```python
from arvel.auth.sessions import EnsureSessionCurrent, stamp_session, logout_other_sessions

# 1) web group, AFTER StartSession and before AuthenticateMiddleware:
kernel.append_to_group("web", EnsureSessionCurrent())   # cache resolved from the container

# 2) right after a successful login, stamp the session:
if await auth.attempt(form, find_user):
    await SessionGuard().login(auth.user(), request)
    await stamp_session(request.session, auth.id())
    ...

# 3) the "sign out my other devices" route:
async def logout_others(request):
    await logout_other_sessions(request, request.user().id)   # bumps the gen, restamps THIS session
    return redirect("/security")
```

It's backed by an atomic per-user counter in the cache, so it needs no session registry. Eviction is
**lazy** — an other device is logged out on its *next* request. It **fails open** (a cache outage
delays eviction rather than logging everyone out), so alert on cache downtime; an un-stamped session
(app not wired for this) is never affected.

## "Log in with Google / Keycloak" (OAuth)

Social / SSO login is a *start* route (redirect to the provider) plus a *callback* route (exchange the
returned code, validate, resolve, log in), built on `OAuthProvider`. It has its own page —
**[OAuth2 Social Login](oauth.md)** — covering provider setup, the redirect/callback routes, the
`state` CSRF check, and completing the login for OIDC vs plain-OAuth providers.

## Token APIs: access + rotating refresh tokens

For a token API you issue a **short-lived access token** plus a **refresh token**, and expose a
`/refresh` endpoint that trades a valid refresh token for a fresh pair. arvel's refresh tokens
**rotate** — each exchange revokes the presented token and issues a new one, so a leaked refresh token
is single-use — and **reuse is detected**: replaying an already-rotated token revokes that user's
whole token family (theft response). Rotation is **atomic**: the revoke is a single
conditional `UPDATE … WHERE revoked = false`, so two concurrent requests presenting the same token can
never both mint a successor — exactly one wins and the other trips reuse detection.

```python
from arvel.auth.refresh import issue_refresh_token, rotate_refresh_token

async def login_api(request):
    credentials = await request.json()
    user = await find_user(credentials)
    if user is None or not await auth.attempt(credentials, find_user):
        return {"error": "invalid"}, 401
    refresh = await issue_refresh_token(user.id)          # plaintext — only the hash is stored
    return {"access_token": mint_access_token(user), "refresh_token": refresh}

async def refresh(request):
    presented = (await request.json())["refresh_token"]
    rotated = await rotate_refresh_token(presented)       # revoke old, issue new
    if rotated is None:
        return {"error": "invalid_grant"}, 401            # unknown or already-used token
    new_refresh, user_id = rotated
    user = await User.find(user_id)
    return {"access_token": mint_access_token(user), "refresh_token": new_refresh}
```

Pair this with short access-token lifetimes — the shorter the access token, the smaller the window
between a permission change and the next refresh (the same staleness tradeoff [SSO roles](idp-roles.md)
have). For minting the access token itself, see [SSO / OIDC](sso-oidc.md) (validating an IdP token) or
[API Tokens](api-tokens.md) (long-lived personal tokens).

## Password reset

`PasswordBroker` (`arvel.auth.password_reset`) is a **stored**, single-use, per-email-throttled
broker — the `PasswordBroker`, not a signed token. A used *or* expired token row is **deleted**,
so a replay never succeeds even inside the original TTL (a stateless signed token, by contrast, stays
replayable until it expires — which is why these are stored, single-use rows). The
`password_reset_tokens` table is a **framework**
migration (`arvel new` ships it, like `users`/`api_tokens`/`failed_jobs`) — no table to author yourself:

```python
from arvel.auth.password_reset import PasswordBroker, PasswordResetStatus
from arvel.security import Hasher

async def find_user(email):
    return await User.where(email=email).first()

broker = PasswordBroker(find_user)   # throttle=60s, ttl=1h by default

async def request_reset(request):
    email = (await request.form())["email"]
    status = await broker.send_reset_link(email)
    # RESET_THROTTLED / INVALID_USER are both fine to fold into the same generic response
    # (don't leak whether the email exists, or that it was just sent moments ago)
    return "If that email exists, a link is on its way."

async def do_reset(request):
    form = await request.form()

    def set_password(user, new_password):
        user.password = Hasher().make(new_password)   # guarded field — set directly

    status = await broker.reset(form["email"], form["token"], form["password"], set_password)
    if status is not PasswordResetStatus.RESET_SUCCESS:
        return "This link is invalid, expired, or already used.", 400
    return redirect("/login")
```

Listen for the events to actually mail the link / notify on completion:

```python
from arvel.auth.password_reset import PasswordReset, PasswordResetRequested
from arvel.support.facades import Event

async def mail_the_link(event: PasswordResetRequested) -> None:
    await mail_reset_link(event.email, f"https://acme.com/reset?email={event.email}&token={event.token}")

Event.listen(PasswordResetRequested, mail_the_link)
Event.listen(PasswordReset, lambda event: audit_password_changed(event.email))
```

A successful `reset()` also **rotates the user's remember token** (`clear_all_remember_tokens`) — a
stolen remember cookie stops working the moment the password is reset — and fires `PasswordReset`.
`send_reset_link` throttles to one send per email per `throttle_seconds` (default 60s) regardless of
whether the previous link was ever used.

## Email verification

Same signed-URL shape as before, but the payload now binds a **hash of the email** the link was issued
for, and the default lifetime is down to **60 minutes** (from 24h)

```python
from arvel.auth.flows import email_verification_token, verify_email_token

async def send_verification(user):
    token = email_verification_token(user.id, user.email, app_secret)
    await mail_verify_link(user.email, f"https://acme.com/verify?token={token}")

async def verify(request):
    # route as e.g. /email/verify/{id} — the path segment says WHICH user, the token PROVES it
    user = await User.find(request.path_param("id"))
    if user is None:
        return "This link is invalid or expired.", 400
    # pass the user's CURRENT email — a changed email invalidates the old link (hash mismatch)
    user_id = verify_email_token(request.query("token"), user.email, app_secret)
    if user_id is None or user_id != user.id:
        return "This link is invalid or expired.", 400
    user.email_verified_at = Date.now()
    await user.save()
    return redirect("/dashboard")
```

## Schema & indexes for the auth token tables

arvel builds each model's `__table__` for *querying*; for **most** token tables the production schema
is yours to create in a migration (the framework ships the [Blueprint](../database/index.md) toolkit,
not the tables) — `password_reset_tokens` is the one exception, shipped as a **framework migration**
(`arvel new` includes it, same as `users`/`api_tokens`/`failed_jobs`) since every app needs it. For the
ones you author yourself, add the columns **plus the integrity/lookup indexes** below — without them
the by-hash lookups table-scan, and `remember_tokens.selector` (the indexed handle the validator is
checked against) lacks the uniqueness its single-row lookup assumes:

```python
from arvel.database.migrations import Migration

class CreateAuthTokenTables(Migration):
    def up(self, schema):
        schema.create("remember_tokens", lambda t: [
            t.id(),
            t.string("selector").unique().index(),   # public handle — UNIQUE + indexed lookup
            t.string("validator"),                    # SHA-256 of the secret half
            t.integer("tokenable_id").index(),
            t.string("expires_at").nullable().index(),
        ])
        schema.create("refresh_tokens", lambda t: [
            t.id(),
            t.string("token").index(),                # SHA-256; looked up by hash on every rotate
            t.integer("tokenable_id").index(),        # family revoke / per-user
            t.boolean("revoked"),
        ])
        schema.create("api_tokens", lambda t: [
            t.id(),
            t.string("name"),
            t.string("token").index(),                # SHA-256; looked up by hash on auth
            t.integer("tokenable_id").index(),
            t.string("abilities"),                    # JSON scopes
            t.string("expires_at").nullable().index(),  # supports prune_expired_tokens()
        ])

    def down(self, schema):
        for table in ("api_tokens", "refresh_tokens", "remember_tokens"):
            schema.drop(table)
```

The **`selector` UNIQUE** constraint is the one that matters for correctness (it guarantees the
single-row lookup behind remember-me); the rest are performance indexes for the hash lookups,
per-user family operations, and expiry pruning. These models declare no timestamps — add
`t.timestamps()` to a table if you want `created_at`/`updated_at`.

## Common mistakes & gotchas

- **Treating a refresh token as reusable.** Rotation makes it single-use, and arvel handles reuse
  for you: replaying an already-rotated token makes `rotate_refresh_token` **revoke that user's whole
  token family** and return `None`, forcing a fresh login. A benign double-submit therefore logs the
  user out — clients should never replay a refresh token.
- **Long-lived verification links.** They're signed and time-boxed — keep `max_age` tight (~1h,
  the default). Don't widen it "to be friendly."
- **Leaking account existence.** Password-reset and login responses should look identical whether or
  not the email is registered — fold `INVALID_USER`/`RESET_THROTTLED` into the same generic copy.
- **Skipping CSRF on session forms.** Session login/logout are state-changing POSTs — protect them.
- **Not re-checking the user.** A token only proves *who*; on every flow re-load the user and confirm
  they still exist and are active before acting.

## How it works

Refresh tokens are rows in `refresh_tokens` storing only a SHA-256 hash; `rotate_refresh_token` looks
up the presented token by hash, and — when it's still active — marks it revoked, saves, and issues a
fresh token (atomic revoke-and-reissue, so each token works exactly once). If the looked-up token is
**already revoked**, that's reuse: `revoke_all_refresh_tokens(user)` kills the whole family and the
call returns `None`. `revoke_all_refresh_tokens` is also handy for "log out of all devices."

`PasswordBroker` stores one `password_reset_tokens` row **per email** (a Hasher hash of the token, plus
`created_at`, which drives both the throttle and the TTL); `send_reset_link` overwrites it past the
throttle window, and `reset` **deletes** it on every terminal outcome (success or expiry) — so a token
is never live for a second use. `flows.py`'s email-verification token is still a **stateless** signed
payload (your app secret) carrying `user_id` + `sha256(email)`, validated with a `max_age` expiry — no
database row to store or clean up, but the email hash means it's invalidated the moment the user's
email changes.

## See also

- [Authentication](authentication.md) — the `attempt` / `login` primitives these routes use.
- [Single Sign-On (OIDC / Keycloak)](sso-oidc.md) — minting access tokens from an IdP.
- [API Tokens](api-tokens.md) — long-lived bearer tokens (vs short access + refresh).
- [Two-Factor Authentication](two-factor.md) — the step to insert between password and session.
