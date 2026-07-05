# Configuration

arvel's auth reads its settings from the `auth.*` config namespace — define them in `config/auth.py`
(a `config = {...}` mapping merged into the dotted-key config repository, read via `config("auth.…")`).
Every knob has a safe built-in default, so configuration is **optional**; set only what you want to change.

## Precedence

For the tunable security knobs, the value is resolved in this order:

1. an **explicit constructor argument** (e.g. `StartSession(secure=False)`) — always wins;
2. otherwise the **`auth.*` config** value, when an app is running;
3. otherwise the **built-in default**.

So a component constructed in a test (no app) uses its built-in default; wired through an app it
honours your config; and an explicit argument overrides both.

## `config/auth.py`

```python
config = {
    # --- identity / providers -------------------------------------------------
    "default_guard": "session",          # which guard guard() returns (session | local | oidc | …)
    "user_model": "app.models.User",     # model for identity resolution (required for the user provider)
    "jit": False,                        # just-in-time provision a user on first SSO login
    "trusted_email_providers": [],       # providers whose verified email may link an existing account

    "oidc": {                            # OIDC guard (required keys; fails loud if incomplete)
        "jwks_uri": "https://idp.example.com/.well-known/jwks.json",
        "issuer":   "https://idp.example.com/",
        "audience": "my-client-id",
        "provider": "oidc",              # optional label on the resulting Principal
    },

    # --- session cookie (StartSession) ---------------------------------------
    "session": {
        "lifetime": 120, # MINUTES; cookie max-age / TTL = x60 (default 2h)
        "secure":      True,             # mark the cookie Secure (HTTPS-only); False for plain-HTTP dev
        "host_prefix": True,             # __Host- cookie prefix (default = secure; requires Secure)
    },

    # --- login lockout (LoginRateLimiter) ------------------------------------
    "lockout": {
        "max_attempts":  5,              # failed logins before lockout
        "decay_seconds": 900,            # lockout window, seconds (default 15m)
        "fail_open":     True,           # on a cache outage: True = allow (alert!), False = deny (DR-0015)
    },

    # --- remember-me (RememberMe / remember()) -------------------------------
    "remember": {
        "ttl":    60 * 60 * 24 * 30,     # remember-cookie lifetime, seconds (default 30d)
        "secure": True,                  # Secure flag on the remember cookie
    },

    # --- sudo / password-confirm (EnsurePasswordConfirmed) -------------------
    "password_timeout": 10800,           # how long a password confirmation stays fresh, seconds (3h)

    # --- impersonation -------------------------------------------------------
    "impersonation": {
        "ability": "impersonate",        # the Gate ability that authorizes "login as"
    },
}
```

## Notes

- **Security defaults are fail-closed.** `session.secure` and `remember.secure` default to `True`;
  only set them `False` for local plain-HTTP development.
- **`lockout.fail_open` is the one availability-over-security default** — on a cache outage logins are
  allowed (so an outage doesn't lock everyone out) but throttling is off, so **alert on cache
  downtime** or set `fail_open = false` to fail closed (decision record DR-0015).
- **`oidc` keys are required when you use the OIDC guard** — a missing `jwks_uri`/`issuer`/`audience`
  raises at construction rather than silently rejecting every token.
- These keys are read where the corresponding component is built; passing the argument explicitly at
  the call site always overrides the config value.

## Framework integration

Auth doesn't reinvent infrastructure — it resolves the framework's own services from the container, so
it honours your app-wide configuration automatically:

| Capability | How auth uses it |
|------------|------------------|
| **Config** (`config("auth.…")`) | All the keys above are read as defaults via the `config` repository — explicit constructor args still win. |
| **Log** (`Log` facade) | Security events are emitted on the **`security`** channel (see the table below). Route that channel to durable storage. |
| **Hash** (`app("hash")`) | Password verification + rehash-on-login resolve the container's hasher (`resolve_hasher()`), so an app-configured Argon2 cost is honoured. |
| **Http** (`app("http")`) | `fetch_userinfo` calls the OIDC userinfo endpoint through the framework HTTP client. |

### Security audit events (`security` log channel)

Identifier-only, best-effort (a logging failure never breaks an auth decision):

| Event | Level | Fields |
|-------|-------|--------|
| `auth.login.succeeded` | info | `user_id` |
| `auth.login.failed` | warning | `identifier` |
| `auth.login.blocked` | warning | `identifier`, `reason=locked_out` |
| `auth.login.locked_out` | warning | `identifier` (the failure that trips the lockout) |
| `auth.refresh.reused` | warning | `tokenable_id` (reuse → family revoked, DR-0014) |
| `auth.remember.theft_detected` | warning | `selector`, `tokenable_id` |
| `auth.impersonation.started` | info | `impersonator_id`, `target_id`, `ability` |
| `auth.impersonation.denied` | warning | `impersonator_id`, `target_id`, `reason` (+ `ability` when unauthorized) |
| `auth.impersonation.stopped` | info | `impersonator_id` |
| `auth.logout_everywhere` | info | `tokenable_id`, `failures` |

## See also

- [Authentication](authentication.md) · [Guards & drivers](guards.md) · [Routes & flows](routes-and-flows.md)
- [Providers & middleware](providers-and-middleware.md) — where these components are wired into the kernel.
