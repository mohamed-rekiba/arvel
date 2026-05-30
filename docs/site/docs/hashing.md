# Hashing

The `Hash` facade turns plaintext passwords into salted hashes that are safe to store. Arvel uses **argon2id** by default (via `argon2-cffi`, a core dependency); **bcrypt** is available as an opt-in extra.

Hashes are **one-way**. There's no "decrypt" — you can only verify a plaintext against an existing hash. That's the whole point.

## Hashing a password

```python
from arvel.facades import Hash


hashed = Hash.make("plain-text-password")
# → "$argon2id$v=19$m=65536,t=3,p=4$..."
```

`Hash.make` returns a string that encodes the algorithm, parameters, salt, and hash. Store the whole string — when you verify later, the parameters are read back from it.

## Verifying a password

```python
ok = Hash.check("plain-text-password", hashed_from_db)
# → True or False
```

Always use `Hash.check`, never `hashed == something`. The check is constant-time and resistant to timing attacks.

## Tuning argon2id

argon2id's memory, time, and parallelism parameters control how expensive hashing is. Higher = more secure, slower. The defaults (65 536 KiB memory, 3 iterations, 4 threads) are roughly ~250 ms on modern hardware.

To tune:

```env
HASH_ARGON2_MEMORY=65536    # KiB; min recommended is 65536
HASH_ARGON2_TIME=3          # iterations
HASH_ARGON2_THREADS=4       # parallelism
```

A useful rule: pick the highest values where login still feels instant (under ~500 ms total round-trip). Refer to [argon2-cffi's tuning guide](https://argon2-cffi.readthedocs.io/en/stable/parameters.html) for benchmarks on your hardware.

If you change the parameters, existing hashes still work — they encode the old values. Use `Hash.needs_rehash` to detect and upgrade them on the next successful login:

```python
@Route.post("/login")
async def login(form: LoginRequest) -> dict:
    payload = form.validated()
    user = await User.find_by_email(payload.email)
    if user is None or not Hash.check(payload.password, user.password_hash):
        raise AuthenticationException("Invalid credentials.")

    if Hash.needs_rehash(user.password_hash):
        user.password_hash = Hash.make(payload.password)
        await user.save()
    ...
```

## Using bcrypt (opt-in)

If you need bcrypt for compatibility with an existing hash store, install the extra:

```bash
pip install "arvel[bcrypt]"
```

Then call `Hash.make_bcrypt()` directly:

```python
hashed = Hash.make_bcrypt("plain-text-password", rounds=12)
# → "$2b$12$..."
```

`Hash.check()` auto-detects the algorithm from the hash prefix and verifies both argon2id and bcrypt hashes, so you can migrate incrementally: keep verifying old bcrypt hashes while issuing new argon2id ones on every successful login.

## Don't roll your own

Never write code like:

```python
# DON'T DO THIS
import hashlib
password_hash = hashlib.sha256(password.encode()).hexdigest()
```

SHA-256 is fast — that's a feature for general-purpose hashing and a bug for password hashing. An attacker who steals your hash table can try billions of guesses per second.

`Hash.make` uses a slow, salted, parameterized algorithm by design. Always use it for passwords.

## What about other one-way digests?

For non-password use cases (deduplicating files, content addressing, integrity checks), use the stdlib directly:

```python
import hashlib

digest = hashlib.sha256(content).hexdigest()
```

`Hash` is specifically for passwords. Don't use it for general-purpose hashing — it's slow on purpose.

## Where to next?

- [Authentication](authentication.md) — uses `Hash` to verify credentials.
- [Password Reset](passwords.md) — the reset flow uses `Hash` for new passwords.
- [Encryption](encryption.md) — when you actually need reversible encoding.
