# Encryption

<a name="introduction"></a>
## Introduction

Arvel's encryption services provide a simple, convenient interface for encrypting and decrypting text via AES-256-GCM. All encrypted values are authenticated, so their underlying value cannot be modified or tampered with once encrypted.

The `Crypt` facade is the entry point. It's also what powers the [`encrypted:*` model casts](../orm/casts.md#encrypted-casting).

<a name="quick-start"></a>
### Quick start

```python
from arvel.database.exceptions import DecryptionError
from arvel.facades import Crypt

token = Crypt.encrypt_string("api-secret")
assert Crypt.decrypt_string(token) == "api-secret"

payload = Crypt.encrypt({"user_id": 1, "scopes": ["read"]})
assert Crypt.decrypt(payload) == {"user_id": 1, "scopes": ["read"]}

try:
    Crypt.decrypt_string(untrusted_token)
except DecryptionError:
    ...  # malformed base64, wrong key, tampered tag — one type for all
```

```bash
arvel key:generate          # write APP_KEY=base64:... to .env
arvel key:generate --show   # print a key without writing
```

| Need | Reach for |
|---|---|
| Encrypt a model column | [`encrypted:*` cast](../orm/casts.md#encrypted-casting) |
| Raw string in app code | `Crypt.encrypt_string` / `decrypt_string` |
| Dict, list, or other JSON value | `Crypt.encrypt` / `decrypt` |
| Tests without a real `.env` | `Crypt.set_encrypter(encrypter)` — pass `None` to restore |

> [!NOTE]
> `Crypt` is always available — no service provider to register. See [Facades](../core-concepts/facades.md#quick-start).

<a name="configuration"></a>
## Configuration

Before using the encrypter, set the `APP_KEY` environment variable. Generate one with:

```bash
arvel key:generate
```

This writes a base64-encoded 32-byte key to your `.env` as `APP_KEY=base64:...`.

> [!WARNING]
> Encryption requires `APP_KEY`. Calling the encrypter without it raises `MissingAppKeyError`. Keep the key secret and out of source control — anyone with it can decrypt your data.

<a name="using-the-encrypter"></a>
## Using the Encrypter

```python
from arvel.facades import Crypt
```

<a name="encrypting-strings"></a>
### Encrypting Strings

```python
ciphertext = Crypt.encrypt_string("secret message")
plaintext = Crypt.decrypt_string(ciphertext)
```

Wrap untrusted ciphertext in a single `except DecryptionError` — the encrypter raises it for every invalid payload (malformed base64, unknown version byte, wrong key, tampered tag).

<a name="encrypting-values"></a>
### Encrypting Values

`encrypt` / `decrypt` handle arbitrary JSON-serializable values — they serialize to JSON, then encrypt:

```python
token = Crypt.encrypt({"user_id": 1, "scopes": ["read", "write"]})
data = Crypt.decrypt(token)   # back to the dict
```

<a name="how-it-works"></a>
## How It Works

The `Encrypter` uses **AES-256-GCM** from the `cryptography` library. The 32-byte key is derived from your `APP_KEY` with HKDF-SHA256. Each encryption produces a self-describing payload — a version byte, a random 12-byte IV, and the authenticated ciphertext — base64-encoded for transport. Decryption raises `DecryptionError` for **any** invalid payload — malformed base64, an unknown version byte, a wrong key, or a tampered tag — so you can wrap a single `except DecryptionError` around untrusted input.

> [!NOTE]
> The application encrypter (`Crypt`, used by `encrypted:*` casts) and the column-level `EncryptedType` decorator use **different wire formats**. They are not interchangeable: data encrypted with one can't be read by the other. Use `Crypt` / `encrypted:*` casts for app-key-backed encryption, and `EncryptedType` only when you manage the raw key yourself.

<a name="generating-and-rotating-keys"></a>
## Generating & Rotating Keys

```bash
arvel key:generate          # write a new APP_KEY to .env
arvel key:generate --show   # print a key without writing it
arvel key:generate --force  # overwrite an existing key
```

> [!WARNING]
> `arvel key:rotate` is **not implemented** — it currently exits with a "not implemented" message. Rotating the application key by hand will make all existing ciphertext (encrypted columns, signed values) unreadable, so plan key changes carefully and re-encrypt data as part of the rotation.
