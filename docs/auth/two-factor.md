# Two-factor authentication

A password proves *something you know* — and that's exactly what gets phished. Two-factor
authentication (2FA) adds *something you have*: a rotating 6-digit code from an authenticator app
(Google Authenticator, 1Password, Aegis…). arvel ships two layers:

- `TwoFactor` — the low-level TOTP primitives (secret generation, the `otpauth://` provisioning URI,
  code verification, recovery-code generation). Use these directly if you want full control.
- The **high-level lifecycle** (`enable_two_factor`/`confirm_two_factor`/`verify_two_factor`/
  `disable_two_factor`/`regenerate_recovery_codes`) plus a **login-challenge state machine** — the
  batteries-included path this page mostly covers, following the standard enable → confirm →
  challenge flow.

!!! note "Needs the `[2fa]` extra"
    2FA uses pyotp — `uv add 'arvel[2fa]'`.

## Before you start: cast the columns

The lifecycle functions store three plain attributes on the `user` you pass in —
`two_factor_secret`, `two_factor_recovery_codes` (a list of *hashed* codes), and
`two_factor_confirmed_at`. arvel does not encrypt these for you: your
user model owns that by declaring the model casts (and a migration adding the three nullable
columns — arvel ships no migration for them, since they live on *your* user model, not a framework
table):

```python
from arvel import Model
from arvel.auth import Authenticatable

class User(Model, Authenticatable):
    __casts__ = {
        "two_factor_secret": "encrypted",
        "two_factor_recovery_codes": "encrypted:array",
        "two_factor_confirmed_at": "datetime",
    }
```

Without those casts the columns hold their values in **plaintext** — add them before shipping 2FA.

## Enrolling a user

`enable_two_factor` generates a secret + a set of recovery codes, stores the secret and the codes'
*hashes* on the user, and returns both in plaintext **once** — show them to the user now:

```python
from arvel.auth.two_factor import enable_two_factor

enrollment = await enable_two_factor(user)
enrollment.provisioning_uri     # "otpauth://totp/arvel:ada@example.com?secret=...&issuer=arvel"
enrollment.recovery_codes       # ["a1b2c3d4e5", ...] — display ONCE, never persisted as plaintext
```

Enabling never auto-confirms — `user.two_factor_confirmed_at` stays unset. Ask the user to enter one
live code to prove they actually scanned it:

```python
from arvel.auth.two_factor import confirm_two_factor

if not await confirm_two_factor(user, submitted_code):
    return "Invalid code", 422
# user.two_factor_confirmed_at is now set — 2FA is enforced at login from here on
```

## The login-challenge state machine

Once `two_factor_confirmed_at` is set, a normal password login must **pause** for the second factor
instead of establishing a full session. `requires_two_factor_challenge` tells you whether to pause;
`begin_two_factor_challenge` is the guard hook — call it *instead of* your usual login (e.g.
`SessionGuard.login`) when it does:

```python
from arvel.auth.two_factor import begin_two_factor_challenge, requires_two_factor_challenge

async def login(request, user):
    if requires_two_factor_challenge(user):
        begin_two_factor_challenge(request, user)  # stashes request.session["auth.2fa.pending"],
        # raises TwoFactorRequired — unreachable below; catch it in your route to redirect
    await SessionGuard().login(user, request)       # only reached when 2FA isn't pending
```

Your app-side `/two-factor-challenge` route renders a code form and completes the challenge:

```python
from arvel.auth.two_factor import complete_two_factor_challenge, pending_two_factor_user_id

async def verify_challenge(request, submitted_code):
    user_id = pending_two_factor_user_id(request)   # who's mid-challenge, from the session
    if user_id is None:
        return "No pending challenge", 400
    user = await User.find(user_id)
    if not await complete_two_factor_challenge(request, user, submitted_code):
        return "Invalid code", 422                  # pending flag is left intact — retry
    await SessionGuard().login(user, request)        # NOW establish the real session
    return redirect("/")
```

arvel ships the state (the pending-session flag + the `TwoFactorRequired` signal) and the guard hook;
the `/two-factor-challenge` route itself — and wiring `begin_two_factor_challenge` into your actual
login handler — is app-side, same as any other route.

## Verifying a code (TOTP or recovery)

`verify_two_factor` accepts either a live TOTP code **or** a recovery code, transparently. A matched
recovery code is consumed — removed from the stored set and re-persisted — so it can never be reused:

```python
from arvel.auth.two_factor import verify_two_factor

await verify_two_factor(user, submitted_code)   # True for a live TOTP code OR an unused recovery code
await verify_two_factor(user, same_recovery_code)  # False the second time — single-use
```

## Recovery codes

Phones get lost. Reissue a fresh set (invalidating the old one) with `regenerate_recovery_codes`:

```python
from arvel.auth.two_factor import regenerate_recovery_codes

new_codes = await regenerate_recovery_codes(user)   # plaintext, once — show them, then discard
```

## Disabling 2FA

```python
from arvel.auth.two_factor import disable_two_factor

await disable_two_factor(user)   # clears the secret, the recovery codes, and confirmed_at
```

## Lower-level: the `TwoFactor` primitives

Everything above is built on `TwoFactor` — reach for it directly if you need more control than the
lifecycle functions give you (a custom storage shape, a non-`Model` user, etc.):

```python
from arvel.auth.two_factor import TwoFactor

secret = TwoFactor.generate_secret()
uri = TwoFactor.provisioning_uri(secret, account_name="ada@example.com", issuer="Acme")
TwoFactor.verify(secret, submitted_code, valid_window=1)   # ± 1 time-step of clock-drift tolerance
TwoFactor.current_code(secret)                             # the code valid right now (handy in tests)
codes = TwoFactor.recovery_codes(count=8)                  # fresh one-time codes to hash + store
```

## Common mistakes & gotchas

- **Storing the secret or recovery codes in plaintext.** Declare the `encrypted`/`encrypted:array`
  casts on your user model *before* calling `enable_two_factor` — arvel doesn't do this for you.
- **Recovery codes that work twice.** `verify_two_factor` already burns them on match — don't build a
  parallel check that skips it.
- **No clock-drift tolerance.** If users report "valid codes rejected," it's usually skew — keep
  `valid_window=1` (the default); don't widen it far, since a larger window lengthens the guess
  surface.
- **Enabling 2FA before confirming a scan.** `enable_two_factor` never auto-confirms; always require
  one valid `confirm_two_factor` call, or a fat-fingered setup locks the user out of their own account.
- **Skipping the login-challenge step.** If your login handler calls `SessionGuard.login` directly
  without checking `requires_two_factor_challenge` first, a confirmed 2FA user logs in on password
  alone — the whole point of the second factor is defeated.

## How it works

`TwoFactor` is a thin wrapper over pyotp (the `[2fa]` extra, imported lazily so it stays out of the
light core): `generate_secret` makes a base32 TOTP secret, `provisioning_uri` formats the standard
`otpauth://` URI, `verify` checks a code within `valid_window` time-steps, `recovery_codes` returns
high-entropy one-time fallbacks. The lifecycle functions layer the higher-level semantics on top: recovery
codes are hashed individually (via the resolved `Hasher`, same as a password) so a leaked table
doesn't expose usable codes; the secret and the recovery-code list are otherwise stored exactly as you
set them — encryption-at-rest is your user model's `encrypted`/`encrypted:array` casts, not something
`two_factor.py` does itself. The challenge state machine is deliberately minimal: a session key
(`auth.2fa.pending`) holding the pending user id, and a `TwoFactorRequired` exception your login route
catches to redirect — no separate persisted "challenge" row.

## See also

- [Authentication](authentication.md) — the password step 2FA layers on top of.
- [Routes & flows](routes-and-flows.md) — wiring the enroll / confirm / challenge steps into real endpoints.
- [Guards & drivers](guards.md) — where the authenticated session is established.
