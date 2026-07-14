# Password Reset

Most applications let users reset a forgotten password. arvel provides a `PasswordBroker` that handles
the security-sensitive parts — throttling, single-use tokens, hashed storage — and leaves the email
delivery and routes to your app.

## Introduction

The broker never stores a plaintext token: it stores a **hash**, enforces a **TTL**, and makes each
token **single-use** (consumed on a successful reset, so a replay always fails). It owns no user
store — you supply a `user_lookup` callback:

```python
from arvel.auth.password_reset import PasswordBroker

broker = PasswordBroker(user_lookup=lambda email: User.where(email=email).first())
```

Tune the windows with `throttle_seconds` (one request per email per window) and `ttl_seconds` (how
long a token stays valid).

## Requesting the reset link

Call `send_reset_link(email)`. It throttles, stores a freshly hashed token, and fires
`PasswordResetRequested` — **your** listener sends the actual email (the broker deliberately doesn't):

```python
async def send_link(request):
    status = await broker.send_reset_link(await request.input("email"))
    return {"status": status.name}
```

Register a listener that mails the token as part of a reset URL (see [Events](../events.md)):

```python
async def on_reset_requested(event: PasswordResetRequested):
    link = route("password.reset", token=event.token, email=event.email)
    await mail_reset_link(event.email, link)
```

The return value is a `PasswordResetStatus` — `RESET_SUCCESS`, `RESET_THROTTLED`, or `INVALID_USER` —
so you can respond without leaking whether an address exists.

## Resetting the password

Call `reset(email, token, new_password, callback)`. The broker verifies the hash and TTL, then invokes
your `callback(user, new_password)` to actually set the password; on success it deletes the token,
rotates the remember token, and fires `PasswordReset`:

```python
async def reset(request):
    status = await broker.reset(
        await request.input("email"),
        await request.input("token"),
        await request.input("password"),
        callback=lambda user, pw: setattr(user, "password", pw),   # hashed cast hashes on write
    )
    return {"status": status.name}   # EXPIRED / INVALID_TOKEN / INVALID_USER / RESET_SUCCESS
```

A used token — or an expired one — always returns a failure status, even within the TTL window, so a
leaked link can't be replayed.

## Security notes

- Tokens are stored **hashed**; the plaintext exists only in the emailed link.
- Reset is **single-use** and **throttled** — brute-force and replay are both closed off.
- A successful reset **rotates the remember token**, invalidating other "remember me" sessions.

## Pruning expired tokens

Used and expired reset records aren't cleared automatically. Run `auth:clear-resets` to delete the
expired ones (keeps the `password_reset_tokens` table small):

```bash
arvel auth:clear-resets
```

Schedule it so it runs itself — e.g. daily (see [Scheduling](../scheduling.md)):

```python
schedule.command("auth:clear-resets").daily()
```

## See also

- [Authentication](authentication.md) — the guards a reset restores access to.
- [Hashing](../hashing.md) — how the token and password are hashed.
- [Events](../events.md) — `PasswordResetRequested` / `PasswordReset`.
