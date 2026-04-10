# Hashing

Passwords belong nowhere near plaintext columns. Arvel’s **`HasherContract`** abstracts password hashing behind **`make`**, **`check`**, and **`needs_rehash`**, with first-class **`BcryptHasher`** and **`Argon2Hasher`** implementations—mirroring Laravel’s `Hash` facade capabilities with explicit typing.

At **v0.1.0**, the security provider selects a driver from **`SecuritySettings`** (for example `bcrypt` vs `argon2`) and constructs the right hasher with cost parameters tuned to your hardware.

## Using the hasher

Inject **`HasherContract`** (or resolve it from the container) wherever you create or verify credentials:

```python
from arvel.security.contracts import HasherContract


def register_user(hasher: HasherContract, password: str) -> str:
    return hasher.make(password)


def verify_login(hasher: HasherContract, password: str, stored: str) -> bool:
    return hasher.check(password, stored)


def should_rehash(hasher: HasherContract, stored: str) -> bool:
    return hasher.needs_rehash(stored)
```

On successful login, if **`should_rehash`** is true, compute **`hasher.make(password)`** once and persist the new hash—plaintext exists only for that request.

## Bcrypt vs Argon2

- **Bcrypt** — battle-tested, widely supported; tune **`rounds`** for your latency budget
- **Argon2** — modern memory-hard winner of the Password Hashing Competition; tune time and memory for defense against GPUs

Pick one as your **default** for new hashes, keep **`needs_rehash`** enabled so older bcrypt hashes migrate on login, and **never** downgrade algorithms silently.

## Constant-time checks

**`check`** uses constant-time comparison where it matters—do not reimplement password verification with raw string equality.

Hashing in Arvel is intentionally small: **one contract**, **two solid drivers**, and a reminder that **secrets management** (pepper keys, HSMs) layers on top when your compliance story requires it.
