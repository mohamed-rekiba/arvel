# Hashing

Never store a password in plaintext, and never roll your own hash. arvel's `Hash` is a driver
manager over battle-tested KDFs — **argon2id** (the default) and **bcrypt** (parity with
Laravel's default, useful when migrating hashes from a PHP app) — with a plaintext-free
`needs_rehash` so you can upgrade a stale hash without ever holding the password again.

## Basic usage

```python
from arvel.support.facades import Hash

hashed = Hash.make("correct horse battery staple")
Hash.check("correct horse battery staple", hashed)  # True
Hash.check("wrong", hashed)                          # False
```

Or construct a manager directly (e.g. in a script, before an app is booted):

```python
from arvel.security import Hasher

hasher = Hasher()          # argon2id, default cost params
hashed = hasher.make("secret")
hasher.check("secret", hashed)
```

## Choosing a driver

`hashing.driver` in config selects `argon2id` (default) or `bcrypt`; `hashing.options` carries
per-driver cost params:

```python
# config/hashing.py
config = {
    "driver": "bcrypt",
    "options": {"rounds": 12},
}
```

```python
from arvel.security import Hasher

Hasher("argon2id", memory_cost=65536, time_cost=3, parallelism=4)
Hasher("bcrypt", rounds=12)
```

## Rehashing without the plaintext

`needs_rehash(hashed)` inspects a stored hash's own embedded parameters — algorithm, cost — and
compares them to the *configured* driver+options. It never takes the plaintext, so you can run it
against every row in a migration script without ever seeing a password:

```python
if Hash.needs_rehash(stored_hash):
    # only after you separately have a verified plaintext (e.g. right after a successful login)
    stored_hash = Hash.make(plain)
```

This is exactly what arvel's own auth flow does: `AuthManager.attempt` calls `needs_rehash` right
after a successful password check and transparently upgrades the stored hash (rehash-on-login).

## Cross-driver migration

`check`/`needs_rehash`/`info`/`is_hashed` all **auto-detect a hash's own driver by its format** —
so switching the configured driver from `bcrypt` to `argon2id` doesn't break existing users. A
bcrypt hash still verifies under an argon2id-configured manager; it's just flagged for upgrade:

```python
manager = Hasher("argon2id")           # newly configured default
manager.check("secret", legacy_bcrypt_hash)        # True — still verifies
manager.needs_rehash(legacy_bcrypt_hash)            # True — wrong driver, upgrade on next login
```

## Inspecting a hash

```python
Hash.is_hashed(hashed)   # True
Hash.is_hashed("secret") # False — not a recognized hash format

info = Hash.info(hashed)
info.algorithm  # "argon2id"
info.options    # {"memory_cost": 65536, "time_cost": 3, "parallelism": 4}
```

## How it works

`HashManager` (re-exported as `Hasher`) holds a *configured* driver (`Argon2Driver`/
`BcryptDriver`, built directly on `argon2-cffi`/`bcrypt` — no abstraction layer in between) used
for `make` and as the `needs_rehash` baseline, plus a default-params instance of every known
driver used only to recognize a hash's own format for `check`/`info`/`is_hashed`. `HashDriver` is
a `Protocol` (`make`/`check`/`needs_rehash`/`info`), so adding a driver is a small, typed class —
no facade or manager changes required.

## See also

- [Encryption](encryption.md) — encrypt/decrypt arbitrary values (not passwords).
- [Authentication](auth/authentication.md) — where rehash-on-login is wired in.
