# Encryption

Arvel provides an encryption service that uses authenticated symmetric encryption (AES-GCM) under the hood. Use it to encrypt strings or bytes that need to survive at rest — column values, signed URLs, opaque tokens passed to third parties.

## App key

All encryption is keyed off `APP_KEY`. Generate one:

```bash
uv run arvel key:generate
```

This writes a 32-byte URL-safe base64 string to your `.env` as `APP_KEY=base64:...`. **Treat the key like a password.** Anyone with the key can decrypt anything your app encrypts.

If you rotate the key, previously-encrypted data is no longer readable. For rotation strategies, see [Key rotation](#key-rotation) below.

## Basic usage

```python
from arvel.facades import Crypto


ciphertext = Crypto.encrypt("hello, world")
plaintext = Crypto.decrypt(ciphertext)
# → "hello, world"
```

`encrypt` accepts `str` or `bytes`; the return value is a URL-safe base64 string.

For bytes-only:

```python
ciphertext = Crypto.encrypt_bytes(b"\x00\x01\x02")
plaintext = Crypto.decrypt_bytes(ciphertext)
```

## Authenticated by default

AES-GCM authenticates the ciphertext — if anyone tampers with even one byte, `decrypt` raises `InvalidCiphertext`. There's no "encrypt without auth" mode.

```python
ciphertext = Crypto.encrypt("hello")
tampered = ciphertext[:-2] + "XX"

try:
    Crypto.decrypt(tampered)
except InvalidCiphertext:
    # someone tampered with the ciphertext
    pass
```

## Encrypted columns

For Arvent model columns whose values must be encrypted at rest, use `EncryptedType`:

```python
from arvel.database import EncryptedType, Model, column, id_, string


class User(Model):
    __tablename__ = "users"

    id: int = id_()
    email: str = string(255)
    api_key: str = column(EncryptedType(key_b64=os.environ["APP_KEY"]))
```

When you write `user.api_key = "..."`, Arvel encrypts on the way in. When you read `user.api_key`, it decrypts on the way out. Queries against the column will only match exact ciphertexts — see [search mode](#search-mode) below for searchable encryption.

The `EncryptedType` uses AES-GCM envelope encryption with a **per-row random IV**. See ADR-014 for the threat model.

### Search mode

For columns you need to query by value (e.g. searching by encrypted email), use deterministic IVs:

```python
api_key: str = column(
    EncryptedType(key_b64=os.environ["APP_KEY"], mode="search"),
)
```

Same plaintext + same key produces the same ciphertext, so equality queries work. **Trade-off**: an attacker who can observe the ciphertext can correlate identical plaintexts. Use random mode by default and only switch to search mode when you actually need it.

## Signed values

For values that don't need to be secret but must be tamper-proof (e.g. a one-time token in a URL), use `Crypto.sign`:

```python
token = Crypto.sign({"user_id": 42, "expires": int(time.time()) + 300})
# → "eyJ...sig=...""

payload = Crypto.unsign(token, max_age=300)
# → {"user_id": 42, "expires": 1763...}
```

`unsign` raises `ExpiredSignature` if `max_age` has passed since the value was signed.

Use signed values for password-reset URLs, magic-link tokens, signed download URLs, anywhere you need short-lived, tamper-proof state that survives a round-trip through an untrusted client.

## Key rotation

!!! info "Planned"
    Staged key rotation — `key:generate --staged`, `key:promote`, `key:retire`, and the multi-key decryption pipeline — is on the roadmap (tracked as FB-022-002). The `arvel key:rotate` command exists at the CLI surface so it shows up in `--help`, but it currently exits `2` with a pointer to the tracking issue rather than re-encrypting columns.

Until the staged-rotation flow ships, key rotation is a manual, one-off procedure:

1. Generate a new key with `arvel key:generate --show` (don't write `.env` yet).
2. Write a migration that reads each `EncryptedType` column with the **old** key, decrypts, and re-encrypts with the **new** key in a single transactional batch per row. Test thoroughly on a copy of production data first.
3. Run the migration with the app stopped (or behind a maintenance gate at your load balancer).
4. Update `APP_KEY` in your environment to the new value and restart.

This is genuinely risky work — any ciphertext you miss becomes unreadable. The roadmap item is what makes this safe and resumable.

## What not to use this for

- **Passwords.** Use [Hashing](hashing.md) — hashing is one-way; encryption is two-way.
- **Long-term secrets in CI logs.** Use your CI's secret store.
- **Things you'll need to search efficiently.** Encrypted columns can only be searched by exact ciphertext (search mode) or by a separate hash column.

## Where to next?

- [Hashing](hashing.md) — for password storage.
- [Authentication](authentication.md) — uses Crypto for signed session cookies.
