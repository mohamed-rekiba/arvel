# Encryption

arvel's `Crypt` encrypts arbitrary values with AES-256-GCM, an **authenticated** cipher (AEAD): a
tampered ciphertext is rejected outright, never silently decrypted into different-but-plausible
data. Values are JSON-serialized before encryption (not pickled) — pickle's own history of
key-leak-to-RCE is exactly what arvel's encryption is designed to avoid.

## Basic usage

```python
from arvel.support.facades import Crypt

token = Crypt.encrypt({"user_id": 1, "roles": ["admin"]})
Crypt.decrypt(token)  # {"user_id": 1, "roles": ["admin"]} — the equal object back

token = Crypt.encrypt_string("a plain string")
Crypt.decrypt_string(token)  # "a plain string" — no JSON envelope
```

Or construct an `Encrypter` directly:

```python
from arvel.security import Encrypter

enc = Encrypter(app_key)
enc.encrypt({"a": 1})
enc.encrypt_string("x")
```

Use `encrypt`/`decrypt` for any JSON-serializable value (dict, list, str, int, bool, `None`);
use `encrypt_string`/`decrypt_string` when you know the value is already a string and don't want
the JSON envelope (e.g. an `encrypted` model cast, or `encryptString` parity).

!!! warning "JSON-serializable values only"
    `encrypt`/`decrypt` go through `json.dumps`/`json.loads`. A value that isn't JSON-serializable
    (e.g. a `datetime`, a custom class) raises before it ever reaches the cipher — serialize it to
    a plain dict/string yourself first.

## Generating a key

```bash
arvel key:generate   # writes APP_KEY to .env in "base64:<...>" form
```

```python
from arvel.security import Encrypter

Encrypter.generate_key()  # "base64:<32 random bytes, base64-encoded>"
```

A key is 32 raw bytes (AES-256). It's accepted either as a `base64:<b64>`-prefixed
string, or as bare base64 (standard or urlsafe alphabet) — whichever decodes to exactly 32 bytes.

## Tamper detection

A single flipped byte anywhere in the payload — nonce or ciphertext — is rejected:

```python
from arvel.security import DecryptionFailed, Encrypter

enc = Encrypter(Encrypter.generate_key())
token = enc.encrypt_string("secret")
tampered = token[:-1] + ("A" if not token.endswith("A") else "B")

try:
    enc.decrypt_string(tampered)
except DecryptionFailed:
    print("rejected — never a silently-wrong plaintext")
```

`DecryptionFailed` is also raised for a malformed payload (wrong number of `.`-separated parts,
invalid base64, an unsupported version prefix) — any input a caller doesn't control gets the same
treatment, never a different exception type leaking why it failed.

## Key rotation

Pass one or more `previous_keys` so ciphertext encrypted under an old key still decrypts, while
new data is always encrypted under the (first) primary key:

```python
from arvel.security import Encrypter

old_key = Encrypter.generate_key()
new_key = Encrypter.generate_key()

old_token = Encrypter(old_key).encrypt_string("secret")

enc = Encrypter(new_key, old_key)     # new primary, old kept for decrypt
enc.decrypt_string(old_token)         # "secret" — still readable

# Re-encrypt an old token under the new primary key, once, e.g. in a migration:
migrated = enc.rotate(old_token)
Encrypter(new_key).decrypt_string(migrated)  # "secret" — now the old key isn't needed at all
```

## Payload format

Every ciphertext is `v1.<base64 nonce>.<base64 ciphertext+tag>` — a version tag (so the format
can evolve), a random 96-bit nonce, and the AES-256-GCM output (ciphertext with the authentication
tag appended, as `cryptography`'s `AESGCM` already does). The nonce is fresh per call to
`encrypt`/`encrypt_string`, so encrypting the same value twice produces different tokens.

## How it works

`Encrypter` wraps `cryptography.hazmat.primitives.ciphers.aead.AESGCM` directly (no Fernet, no
pickle). `encrypt`/`decrypt` add a `{"j": value}` JSON envelope around the plaintext before
sealing it; `encrypt_string`/`decrypt_string` seal/open raw bytes. Decryption tries each held key
in order (primary first) and only raises `DecryptionFailed` once every key's AEAD tag check has
failed — so `previous_keys` and `rotate` cost nothing on the common (primary-key) path.

## See also

- [Hashing](hashing.md) — for passwords; never `encrypt` a password, `Hash.make` it.
- [Configuration](configuration.md) — where `APP_KEY` is read from.

!!! note "High-volume nonce budget"
    Each encryption draws a random 96-bit GCM nonce. Per NIST SP 800-38D, keep a single
    key under ~2^32 encryptions to make nonce collision negligible — rotate `APP_KEY`
    (the `previous_keys` mechanism keeps old ciphertext readable) well before that.
