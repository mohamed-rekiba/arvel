# Encryption

Hashing protects passwords; **encryption** protects secrets you must recover—OAuth tokens at rest, integration credentials, PII fields your domain genuinely needs to round-trip. Arvel exposes **`EncrypterContract`** with a default **`AesEncrypter`** implementation (**AES-256-CBC** with **HMAC** for integrity).

Encrypt only what you must—every ciphertext expands operational risk (key rotation, backup exposure). Prefer hashing or tokenization when you do not need the plaintext back.

## The contract

**`EncrypterContract`** defines:

- **`encrypt(value: str) -> str`** — returns a **Base64** payload that includes integrity data
- **`decrypt(payload: str) -> str`** — verifies MAC before returning plaintext; raises on tampering

```python
from arvel.security.contracts import EncrypterContract


def store_integration_secret(encrypter: EncrypterContract, raw: str) -> str:
    return encrypter.encrypt(raw)


def use_integration_secret(encrypter: EncrypterContract, stored: str) -> str:
    return encrypter.decrypt(stored)
```

## AES encrypter

**`AesEncrypter`** implements the contract with symmetric keys from your **`SecuritySettings`** (or equivalent module config). **Rotate keys** with a strategy: decrypt with old, re-encrypt with new, track a key id in the payload if you outgrow single-key deployments.

## Operational practices

- Load keys from **environment or a secret manager**, never from git
- Restrict **who can decrypt** in production—separate data access roles
- Log **access patterns**, not plaintext
- Plan **breach response**: compromised key means re-encrypt everything it touched

Encryption in Arvel is deliberately **boring cryptography wrapped in clear contracts**—so your application code stays readable while HMAC and cipher details stay centralized in one place.
