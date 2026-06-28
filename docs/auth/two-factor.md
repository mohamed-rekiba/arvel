# Two-factor authentication

A password proves *something you know* — and that's exactly what gets phished. Two-factor
authentication (2FA) adds *something you have*: a rotating 6-digit code from an authenticator app
(Google Authenticator, 1Password, Aegis…). arvel's `TwoFactor` covers the standard TOTP flow —
generate a secret, show the user a QR code, verify their codes at login — plus one-time recovery
codes for when they lose their phone.

!!! note "Install the extra"
    2FA uses pyotp, which ships in the `[2fa]` extra:

    ```bash
    uv add 'arvel[2fa]'
    ```

## Enrolling a user

Generate a secret, store it on the user, and show them a QR code to scan. The `provisioning_uri` is
the `otpauth://` string every authenticator app understands — render it as a QR:

```python
from arvel.auth.two_factor import TwoFactor

secret = TwoFactor.generate_secret()                 # store this on the user (encrypted!)
uri = TwoFactor.provisioning_uri(secret, account_name="ada@example.com", issuer="Acme")
# uri → "otpauth://totp/Acme:ada@example.com?secret=...&issuer=Acme"  → render as a QR code
```

Before you turn 2FA on, confirm the user actually scanned it by asking them to enter one code:

```python
if TwoFactor.verify(secret, submitted_code):
    user.two_factor_secret = secret
    user.two_factor_enabled = True
    await user.save()
```

## Verifying at login

After the password step succeeds, require a current code. `verify` accepts a small `valid_window` to
tolerate clock drift between the server and the user's phone (1 = ±1 time-step, the default):

```python
if not TwoFactor.verify(user.two_factor_secret, submitted_code, valid_window=1):
    return "Invalid code", 401
auth.login(user)
```

`TwoFactor.current_code(secret)` returns the code valid right now — handy in tests so you don't have
to wait for a real authenticator.

## Recovery codes

Phones get lost. Issue a set of one-time recovery codes at enrollment, show them once, and store only
their hashes (treat them exactly like passwords):

```python
codes = TwoFactor.recovery_codes(count=8)            # ["a1b2c3d4", ...] — display ONCE
user.recovery_codes = [Hasher().make(c) for c in codes]
await user.save()
```

At login, accept a recovery code as an alternative to a TOTP code — and **burn it** after use so each
works only once.

## Common mistakes & gotchas

- **Storing the secret in plaintext.** The TOTP secret *is* the second factor — encrypt it at rest.
  A leaked secret column defeats the whole point.
- **Recovery codes that work twice.** They must be single-use: verify against the stored hashes and
  remove the one that matched. Show them once, never again.
- **No clock-drift tolerance.** If users report "valid codes rejected," it's usually skew — keep
  `valid_window=1`; don't widen it far, since a larger window lengthens the guess surface.
- **Enabling 2FA before confirming a scan.** Require one valid code at enrollment, or a fat-fingered
  setup locks the user out of their own account.

## How it works

`TwoFactor` is a thin wrapper over pyotp (the `[2fa]` extra, imported lazily so it stays out of the
light core). `generate_secret` makes a base32 TOTP secret; `provisioning_uri` formats the standard
`otpauth://` URI for authenticator apps; `verify` checks a submitted code against the secret within
`valid_window` time-steps; `current_code` computes the code for the current step; `recovery_codes`
returns high-entropy one-time fallbacks. The secret lives on your user model — arvel computes and
checks codes, your app owns storage and the enable/disable lifecycle.

## See also

- [Authentication](authentication.md) — the password step 2FA layers on top of.
- [Routes & flows](routes-and-flows.md) — wiring the enroll / verify steps into real endpoints.
- [Guards & drivers](guards.md) — where the authenticated session is established.
